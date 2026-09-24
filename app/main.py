from pathlib import Path
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import BackgroundTasks, FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from app.core.config import settings
from app.db.session import engine
from app.api.v1.api import api_router
from app.workers.scheduler import start_scheduler, stop_scheduler
from scripts.run_pipeline import run_pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("App")
pipeline_state = {"status": "idle", "started_at": None, "finished_at": None, "error": None}


def _allowed_origins() -> list[str]:
    raw = getattr(settings, "CORS_ALLOWED_ORIGINS", "")
    if isinstance(raw, list):
        return raw
    return [item.strip() for item in str(raw).split(",") if item.strip()]


def _admin_token_configured() -> bool:
    return bool(getattr(settings, "ADMIN_API_TOKEN", None) or os.getenv("ADMIN_API_TOKEN"))


def _require_admin(request: Request) -> None:
    expected = getattr(settings, "ADMIN_API_TOKEN", None) or os.getenv("ADMIN_API_TOKEN")
    if not expected:
        raise HTTPException(status_code=503, detail="Administrative API is not configured")
    supplied = request.headers.get("X-Admin-Token")
    if not supplied or supplied != expected:
        raise HTTPException(status_code=401, detail="Administrative authorization required")


templates_dir = Path(__file__).resolve().parent / "ui" / "templates"
templates = Jinja2Templates(directory=str(templates_dir))


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.APP_NAME}...")
    with engine.connect() as conn:
        res = conn.execute(text("SELECT current_database(), current_user;")).fetchone()
        logger.info(f"Connected to PostgreSQL: Database={res[0]}, User={res[1]}")
    start_scheduler()
    yield
    logger.info("Stopping application...")
    stop_scheduler()


app = FastAPI(
    title=settings.APP_NAME,
    description="FMCG Competitor Promotion Intelligence API & Dashboard",
    version="1.0.0",
    lifespan=lifespan,
)

origins = _allowed_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=bool(origins),
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Admin-Token"],
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/", response_class=HTMLResponse)
def get_dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="dashboard.html", context={"app_name": settings.APP_NAME})


@app.get("/health")
def health_check():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1;"))
    return {"status": "ok", "app": settings.APP_NAME, "env": settings.APP_ENV}


def _run_pipeline_job():
    pipeline_state.update(status="running", started_at=datetime.now(timezone.utc).isoformat(), finished_at=None, error=None)
    try:
        run_pipeline(crawl_fresh=True, max_docs=5)
        pipeline_state["status"] = "completed"
    except Exception as exc:
        logger.exception("Manual pipeline failed")
        pipeline_state.update(status="failed", error=str(exc))
    finally:
        pipeline_state["finished_at"] = datetime.now(timezone.utc).isoformat()


@app.post("/api/v1/pipeline/run", status_code=202)
def run_pipeline_now(request: Request, background_tasks: BackgroundTasks):
    _require_admin(request)
    if pipeline_state["status"] == "running":
        return {"status": "running", "message": "A promotion scan is already running."}
    background_tasks.add_task(_run_pipeline_job)
    return {"status": "queued", "message": "Promotion scan queued. Use /api/v1/pipeline/status to monitor it."}


@app.get("/api/v1/pipeline/status")
def pipeline_status():
    return pipeline_state
