import logging
from apscheduler.schedulers.background import BackgroundScheduler
from app.core.config import settings
from app.db.session import SessionLocal
from app.services.ranking.rescore import rescore_promotions
from app.workers.expiration import run_expiration_check
from scripts.run_pipeline import run_pipeline

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler()


def scheduled_expiration_job():
    db = SessionLocal()
    try:
        run_expiration_check(db)
        rescore_promotions(db)
        db.commit()
    except Exception as e:
        logger.exception("Error in expiration job: %s", e)
        db.rollback()
    finally:
        db.close()


def scheduled_pipeline_job():
    try:
        run_pipeline(crawl_fresh=True, max_docs=None)
    except Exception:
        logger.exception("Error in scheduled pipeline job")


def start_scheduler():
    scheduler.add_job(
        scheduled_expiration_job,
        "interval",
        minutes=settings.EXPIRATION_CHECK_MINUTES,
        id="expiration_checker",
        replace_existing=True
    )
    scheduler.add_job(
        scheduled_pipeline_job,
        "interval",
        minutes=settings.CRAWL_INTERVAL_MINUTES,
        id="pipeline_runner",
        replace_existing=True
    )
    scheduler.start()
    logger.info(
        "Background scheduler started (Expiration: %sm, Crawl: %sm).",
        settings.EXPIRATION_CHECK_MINUTES, settings.CRAWL_INTERVAL_MINUTES,
    )


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Background scheduler stopped.")
