from pathlib import Path
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional
from fastapi import BackgroundTasks, Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from app.core.config import settings
from app.core.deps import Principal, get_principal_optional, require_admin_session_or_key, require_role
from app.db.session import engine
from app.api.v1.api import api_router
from app.workers.scheduler import start_scheduler, stop_scheduler
from scripts.run_pipeline import run_pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("App")
pipeline_state = {"status": "idle", "started_at": None, "finished_at": None, "error": None}

templates_dir = Path(__file__).resolve().parent / "ui" / "templates"
templates = Jinja2Templates(directory=str(templates_dir))


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.APP_NAME}...")
    # Verify DB connectivity on startup
    with engine.connect() as conn:
        res = conn.execute(text("SELECT current_database(), current_user;")).fetchone()
        logger.info(f"Connected to PostgreSQL: Database={res[0]}, User={res[1]}")

    # Start background scheduler for periodic crawling & expiration checking
    start_scheduler()
    yield
    logger.info("Stopping application...")
    stop_scheduler()


_is_prod = settings.APP_ENV.lower() == "production"
app = FastAPI(
    title=settings.APP_NAME,
    description="FMCG Competitor Promotion Intelligence API & Dashboard",
    version="1.1.0",
    lifespan=lifespan,
    # Interactive API docs are for development only.
    docs_url=None if _is_prod else "/docs",
    redoc_url=None if _is_prod else "/redoc",
    openapi_url=None if _is_prod else "/openapi.json",
)

# The bundled dashboard is same-origin. Extra origins must be listed explicitly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key", "X-CSRF-Token"],
)

# Full policy is report-only until checked in a real browser console (the UI loads Tailwind and
# Font Awesome from CDNs); the clickjacking/base/form directives are enforced.
_CSP_ENFORCED = "frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'"
_CSP_REPORT_ONLY = (
    "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com; "
    "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; font-src https://cdnjs.cloudflare.com; "
    "img-src 'self' data:; connect-src 'self'"
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    h = response.headers
    h.setdefault("X-Content-Type-Options", "nosniff")
    h.setdefault("X-Frame-Options", "DENY")
    h.setdefault("Referrer-Policy", "same-origin")
    h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    h.setdefault("Content-Security-Policy", _CSP_ENFORCED)
    h.setdefault("Content-Security-Policy-Report-Only", _CSP_REPORT_ONLY)
    if settings.session_cookie_secure:
        h.setdefault("Strict-Transport-Security", "max-age=31536000")
    if request.url.path.startswith("/api/v1/auth") or request.url.path in ("/", "/login", "/account"):
        h.setdefault("Cache-Control", "no-store")
    return response


# Mount REST API
app.include_router(api_router, prefix="/api/v1")


def _page(request: Request, name: str, principal: Optional[Principal], **context):
    return templates.TemplateResponse(
        request=request, name=name, context={"app_name": settings.APP_NAME, "user": principal.user if principal else None, **context}
    )


def _protected_page(request: Request, name: str, principal: Optional[Principal], minimum: str = "VIEWER", **context):
    """Serve an HTML page to logged-in users; everyone else is sent to the login page."""
    from app.services.auth import role_allows
    if principal is None:
        return RedirectResponse("/login", status_code=303)
    from app.services import mfa as mfa_service
    if (principal.user.must_change_password or mfa_service.setup_required(principal.user)) and name != "account.html":
        return RedirectResponse("/account", status_code=303)
    if not role_allows(principal.user, minimum):
        return RedirectResponse("/", status_code=303)
    return _page(request, name, principal, **context)


@app.get("/", response_class=HTMLResponse)
def get_dashboard(request: Request, principal: Optional[Principal] = Depends(get_principal_optional)):
    return _protected_page(request, "dashboard.html", principal)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, principal: Optional[Principal] = Depends(get_principal_optional)):
    if principal is not None:
        return RedirectResponse("/", status_code=303)
    return _page(request, "login.html", None)


@app.get("/account", response_class=HTMLResponse)
def account_page(request: Request, principal: Optional[Principal] = Depends(get_principal_optional)):
    return _protected_page(request, "account.html", principal)


@app.get("/insights", response_class=HTMLResponse)
def insights_page(request: Request, principal: Optional[Principal] = Depends(get_principal_optional)):
    return _protected_page(request, "insights.html", principal)


@app.get("/compare", response_class=HTMLResponse)
def compare_page(request: Request, principal: Optional[Principal] = Depends(get_principal_optional)):
    return _protected_page(request, "compare.html", principal, minimum="ANALYST")


@app.get("/review", response_class=HTMLResponse)
def review_page(request: Request, principal: Optional[Principal] = Depends(get_principal_optional)):
    return _protected_page(request, "review.html", principal, minimum="ANALYST")


@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request, principal: Optional[Principal] = Depends(get_principal_optional)):
    return _protected_page(request, "admin.html", principal, minimum="ADMIN")


@app.get("/health")
def health_check():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1;"))
    return {"status": "ok"}


def _run_pipeline_job():
    pipeline_state.update(status="running", started_at=datetime.now(timezone.utc).isoformat(), finished_at=None, error=None)
    try:
        # A fresh crawl processes every document it produced (max_docs=None).
        result = run_pipeline(crawl_fresh=True, max_docs=None)
        if result.get("status") == "busy":
            pipeline_state.update(status="completed", error="Another scan was already running; nothing new was started.")
        else:
            pipeline_state["status"] = "completed"
            pipeline_state["summary"] = result
    except Exception:
        # Details stay in the server log; the public status endpoint must not leak internals.
        logger.exception("Manual pipeline failed")
        pipeline_state.update(status="failed", error="Scan failed. See server logs for details.")
    finally:
        pipeline_state["finished_at"] = datetime.now(timezone.utc).isoformat()


@app.post("/api/v1/pipeline/run", status_code=202, dependencies=[Depends(require_admin_session_or_key)])
def run_pipeline_now(background_tasks: BackgroundTasks):
    if pipeline_state["status"] in ("running", "queued"):
        return {"status": pipeline_state["status"], "message": "A promotion scan is already running."}
    pipeline_state.update(status="queued", started_at=None, finished_at=None, error=None)
    background_tasks.add_task(_run_pipeline_job)
    return {"status": "queued", "message": "Promotion scan queued. Use /api/v1/pipeline/status to monitor it."}


@app.get("/api/v1/pipeline/status", dependencies=[Depends(require_role("VIEWER"))])
def pipeline_status():
    # Status is tracked per process; run a single uvicorn worker (see scripts/start_server.sh).
    return pipeline_state
