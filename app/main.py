from pathlib import Path
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from app.core.config import settings
from app.db.session import engine
from app.api.v1.api import api_router
from app.workers.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("App")

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
