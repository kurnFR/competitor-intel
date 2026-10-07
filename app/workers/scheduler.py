import logging
from apscheduler.schedulers.background import BackgroundScheduler
from app.core.config import settings
from app.db.session import SessionLocal
from app.services.alerts import check_and_alert
from app.services.auth import purge_expired_sessions
from app.services.digest import digest_configured, send_digest
from app.services.ranking.rescore import rescore_promotions
from app.services.retention import run_retention
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
        purge_expired_sessions(db)
        check_and_alert(db)
    except Exception as e:
        logger.exception("Error in expiration job: %s", e)
        db.rollback()
    finally:
        db.close()


def scheduled_pipeline_job():
    try:
        run_pipeline(crawl_fresh=True, max_docs=None, only_due=True, trigger="SCHEDULED")
    except Exception:
        logger.exception("Error in scheduled pipeline job")


def scheduled_retention_job():
    db = SessionLocal()
    try:
        run_retention(db)
    except Exception:
        logger.exception("Error applying the retention policy")
        db.rollback()
    finally:
        db.close()


def scheduled_digest_job():
    db = SessionLocal()
    try:
        send_digest(db)
    except Exception:
        logger.exception("Error sending digest")
    finally:
        db.close()


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
        minutes=settings.SCHEDULER_TICK_MINUTES,
        id="pipeline_runner",
        replace_existing=True
    )
    if settings.RETENTION_ENABLED:
        scheduler.add_job(scheduled_retention_job, "cron", hour=settings.RETENTION_HOUR, minute=30, id="retention", replace_existing=True)
    if digest_configured():
        scheduler.add_job(
            scheduled_digest_job, "cron", day_of_week=settings.DIGEST_DAY_OF_WEEK, hour=settings.DIGEST_HOUR,
            id="weekly_digest", replace_existing=True,
        )
        logger.info("Weekly digest scheduled (%s at %02d:00).", settings.DIGEST_DAY_OF_WEEK, settings.DIGEST_HOUR)
    scheduler.start()
    logger.info(
        "Background scheduler started (expiry check every %sm; sources checked for due crawls every %sm).",
        settings.EXPIRATION_CHECK_MINUTES, settings.SCHEDULER_TICK_MINUTES,
    )


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Background scheduler stopped.")
