"""Keep the database and disk from growing forever, without losing anything that matters.

Removed after RETENTION_DOCUMENT_DAYS: the raw stored file and the full page text of OLD crawled pages.
Kept: the page's address, time, hash and size, every promotion, its evidence quote and source link, every observation.
Never removed, whatever the age: the NEWEST page of each website (the next scan compares against it to know whether the
page changed; losing it would stop unchanged promotions from being re-confirmed).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy import and_, exists
from sqlalchemy.orm import Session, aliased

from app.core.config import settings
from app.models.alert import AlertEvent
from app.models.auth import AuditLog
from app.models.scan_run import ScanRun
from app.models.source import CrawlDocument
from app.services.storage import RawDocumentStore, get_raw_document_store

logger = logging.getLogger(__name__)
MIN_DOCUMENT_DAYS = 14


def document_days() -> int:
    if settings.RETENTION_DOCUMENT_DAYS < MIN_DOCUMENT_DAYS:
        logger.warning("RETENTION_DOCUMENT_DAYS=%s is below the safe minimum; using %s.", settings.RETENTION_DOCUMENT_DAYS, MIN_DOCUMENT_DAYS)
    return max(MIN_DOCUMENT_DAYS, settings.RETENTION_DOCUMENT_DAYS)


def run_retention(db: Session, *, dry_run: bool = False, now: Optional[datetime] = None,
                  store: Optional[RawDocumentStore] = None) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    store = store or get_raw_document_store()
    cutoff = now - timedelta(days=document_days())

    newer = aliased(CrawlDocument)
    has_newer_version = exists().where(and_(newer.source_id == CrawlDocument.source_id, newer.url == CrawlDocument.url,
                                            newer.retrieved_at > CrawlDocument.retrieved_at))
    candidates = (
        db.query(CrawlDocument)
        .filter(CrawlDocument.retrieved_at < cutoff, has_newer_version,
                (CrawlDocument.text_content.isnot(None)) | (CrawlDocument.raw_content_uri.isnot(None)))
        .all()
    )
    purge_ids = {d.id for d in candidates}
    # A stored file may be shared by several page records; keep it while any record we are NOT purging still points at it.
    still_used = {u for (u,) in db.query(CrawlDocument.raw_content_uri).filter(
        CrawlDocument.raw_content_uri.isnot(None), ~CrawlDocument.id.in_(purge_ids or {None})).all()}

    files = text_chars = bytes_freed = 0
    seen_files = set()
    for doc in candidates:
        text_chars += len(doc.text_content or "")
        uri = doc.raw_content_uri
        deletable = uri is not None and uri not in still_used
        if deletable and uri not in seen_files:
            seen_files.add(uri)
            freed = (doc.raw_content_size_bytes or 0) if dry_run else store.delete(uri)
            bytes_freed += freed
            files += 1
        if not dry_run:
            doc.text_content = None
            if deletable:
                doc.raw_content_uri = None
            doc.metadata_json = {**(doc.metadata_json or {}), "retention_purged_at": now.isoformat()}

    def prune(model, column, days):
        q = db.query(model).filter(column < now - timedelta(days=days))
        n = q.count()
        if n and not dry_run:
            q.delete(synchronize_session=False)
        return n

    result = {
        "dry_run": dry_run,
        "documents_trimmed": len(candidates), "raw_files_removed": files, "bytes_freed": bytes_freed, "text_characters_freed": text_chars,
        "audit_log_rows": prune(AuditLog, AuditLog.occurred_at, settings.RETENTION_AUDIT_DAYS),
        "scan_runs": prune(ScanRun, ScanRun.started_at, settings.RETENTION_SCAN_RUN_DAYS),
        "alert_events": prune(AlertEvent, AlertEvent.created_at, settings.RETENTION_ALERT_DAYS),
    }
    if not dry_run:
        db.commit()
        logger.info("Retention: %s", result)
    return result
