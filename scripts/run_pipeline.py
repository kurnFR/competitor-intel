import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import SessionLocal, engine
from app.models.promotion import Promotion, PromotionObservation
from app.models.scan_run import ScanRun
from app.models.source import CrawlDocument, SourceRegistry
from app.services.crawler.manager import run_all_crawlers
from app.services.pipeline_core import process_document
from app.services.entity_resolution.resolver import EntityResolver
from app.services.extraction.llm_extractor import LLMExtractor
from app.services.ranking.rescore import rescore_promotions

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("Pipeline")

# Arbitrary constant identifying the pipeline's cross-process advisory lock.
_PIPELINE_LOCK_KEY = 7_204_118_301
_GOOD_STATUSES = {"SUCCESS", "PARTIAL_SUCCESS"}


def _acquire_lock():
    """Take a Postgres advisory lock on a dedicated connection.

    Prevents the scheduler, a manual "Scan now" and extra uvicorn workers from
    running the pipeline at the same time. Returns (connection, acquired).
    """
    conn = engine.connect()
    if engine.dialect.name != "postgresql":
        return conn, True
    acquired = bool(conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _PIPELINE_LOCK_KEY}).scalar())
    conn.commit()
    return conn, acquired


def _release_lock(conn, acquired: bool) -> None:
    try:
        if acquired and engine.dialect.name == "postgresql":
            conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _PIPELINE_LOCK_KEY})
            conn.commit()
    finally:
        conn.close()


def _start_run(trigger: str, triggered_by: Optional[str]):
    """Record the run in its own session so it is visible immediately and survives a rollback of the main one."""
    session = SessionLocal()
    try:
        run = ScanRun(trigger=trigger, triggered_by=triggered_by, status="RUNNING")
        session.add(run)
        session.commit()
        return run.id
    except Exception:
        logger.exception("Could not record scan start")
        session.rollback()
        return None
    finally:
        session.close()


def _finish_run(run_id, status: str, *, summary: Optional[dict] = None, error: Optional[str] = None) -> None:
    if run_id is None:
        return
    session = SessionLocal()
    try:
        session.query(ScanRun).filter(ScanRun.id == run_id).update(
            {"status": status, "finished_at": datetime.now(timezone.utc), "summary": summary, "error": (error or None) and error[:1000]},
            synchronize_session=False)
        session.commit()
    except Exception:
        logger.exception("Could not record scan result")
        session.rollback()
    finally:
        session.close()


def _touch_promotions_for_document(db: Session, document_id, now: datetime) -> int:
    """An unchanged page that was just re-fetched still confirms its promotions."""
    ids = db.query(PromotionObservation.promotion_id).filter(PromotionObservation.document_id == document_id)
    return (
        db.query(Promotion)
        .filter(Promotion.id.in_(ids), Promotion.status.in_(["ACTIVE", "UNKNOWN"]))
        .update({"last_seen_at": now, "last_verified_at": now}, synchronize_session=False)
    )


def run_pipeline(
    crawl_fresh: bool = False,
    max_docs: Optional[int] = 3,
    force: bool = False,
    only_due: bool = False,
    trigger: str = "CLI",
    triggered_by: Optional[str] = None,
) -> Dict[str, Any]:
    """Crawl (optionally), extract, validate and store promotions.

    Raises on failure so callers (API, scheduler, CLI) can report it truthfully.
    Returns a summary dict; ``status`` is "completed" or "busy" (another run is active).

    max_docs only limits re-processing of stored documents; a fresh crawl always
    processes every document it produced. Documents already processed from an
    identical page are skipped (their promotions are just marked as still seen)
    unless force=True.
    """
    lock_conn, acquired = _acquire_lock()
    if not acquired:
        _release_lock(lock_conn, acquired)
        logger.warning("Pipeline already running in another process; skipping this run.")
        return {"status": "busy"}

    db: Session = SessionLocal()
    run_id = _start_run(trigger, triggered_by)
    summary: Dict[str, Any] = {
        "status": "completed", "documents": 0, "documents_skipped_unchanged": 0,
        "documents_failed": 0, "extracted": 0, "observations": 0, "created": 0,
        "rejected": 0, "review_items": 0, "cards_truncated": 0,
    }
    try:
        logger.info("Starting Competitor Intel Extraction & Promotion Pipeline...")

        if crawl_fresh:
            logger.info("Executing active crawlers...")
            docs = run_all_crawlers(db, only_due=only_due)
        else:
            query = db.query(CrawlDocument).order_by(CrawlDocument.retrieved_at.desc())
            docs = query.limit(max_docs).all() if max_docs else query.all()
            if not docs:
                logger.info("No existing documents found. Triggering crawlers...")
                docs = run_all_crawlers(db, only_due=only_due)
                crawl_fresh = True

        logger.info("Processing %d documents through AI Extraction & Validation...", len(docs))
        summary["documents"] = len(docs)

        source_ok: Dict[Any, bool] = {}        # source_id -> every document of that source succeeded in this run
        extractor = LLMExtractor()
        resolver = EntityResolver(db)

        for doc in docs:
            logger.info("Document %s (%s) text length: %d", doc.id, doc.url, len(doc.text_content or ""))
            if not doc.text_content:
                continue

            now = datetime.now(timezone.utc)
            already_done = bool((doc.metadata_json or {}).get("pipeline_processed_at"))
            if already_done and not force:
                if crawl_fresh:
                    _touch_promotions_for_document(db, doc.id, now)
                    source_ok.setdefault(doc.source_id, True)
                    db.commit()
                summary["documents_skipped_unchanged"] += 1
                logger.info("Document %s unchanged since last extraction; skipping LLM call.", doc.id)
                continue

            source = doc.source or db.query(SourceRegistry).filter(SourceRegistry.id == doc.source_id).first()
            reliability = source.reliability_score if source else 0.85

            doc_ok = process_document(db, doc, extractor=extractor, resolver=resolver, reliability=reliability, summary=summary)

            source_ok[doc.source_id] = source_ok.get(doc.source_id, True) and doc_ok
            if doc_ok:
                doc.metadata_json = {**(doc.metadata_json or {}), "pipeline_processed_at": now.isoformat()}
            else:
                summary["documents_failed"] += 1
                logger.warning("Document %s had extraction errors and will be retried next run.", doc.id)
            db.commit()

        # A source counts as "processed" only if every one of its pages was collected and extracted (or confirmed
        # unchanged). A failed crawl or failed extraction is never evidence that a promotion has disappeared.
        finished = datetime.now(timezone.utc)
        for sid, ok in source_ok.items():
            if ok and sid is not None:
                db.query(SourceRegistry).filter(SourceRegistry.id == sid).update({"last_processed_at": finished}, synchronize_session=False)
        db.commit()

        # Keep freshness-based ranking current after this run.
        rescored = rescore_promotions(db)
        db.commit()
        logger.info("Rescored %d promotions.", rescored)

        logger.info("Pipeline execution finished! %s", summary)
        _finish_run(run_id, "COMPLETED" if not summary["documents_failed"] else "PARTIAL", summary=summary)
        return summary

    except Exception as exc:
        logger.exception("Pipeline error")
        db.rollback()
        _finish_run(run_id, "FAILED", summary=summary, error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        db.close()
        _release_lock(lock_conn, acquired)


if __name__ == "__main__":
    try:
        result = run_pipeline()
    except Exception:
        sys.exit(1)
    sys.exit(0 if result.get("status") in ("completed", "busy") else 1)
