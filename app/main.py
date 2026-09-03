from pathlib import Path
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import BackgroundTasks, FastAPI, Request
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


app = FastAPI(
    title=settings.APP_NAME,
    description="FMCG Competitor Promotion Intelligence API & Dashboard",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount REST API
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
def run_pipeline_now(background_tasks: BackgroundTasks):
    if pipeline_state["status"] == "running":
        return {"status": "running", "message": "A promotion scan is already running."}
    background_tasks.add_task(_run_pipeline_job)
    return {"status": "queued", "message": "Promotion scan queued. Use /api/v1/pipeline/status to monitor it."}


@app.get("/api/v1/pipeline/status")
def pipeline_status():
    return pipeline_state
