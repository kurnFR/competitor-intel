"""Small durable worker loop for CrawlJob retry/resume processing.

The worker deliberately accepts a processor callback. Source-specific crawling
stays in crawler adapters while this module owns queue state transitions.
"""

import logging
from datetime import datetime
from typing import Callable, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.source import CrawlJob
from app.services.crawler.job_errors import CrawlJobError
from app.services.crawler.job_queue import (
    claim_retryable_jobs,
    mark_job_failure,
    mark_job_running,
    mark_job_success,
)

logger = logging.getLogger(__name__)

JobProcessor = Callable[[CrawlJob], Tuple[Optional[int], Optional[str]]]


def process_retryable_jobs(
    db: Session,
    worker_id: str,
    processor: JobProcessor,
    now: Optional[datetime] = None,
    limit: int = 10,
) -> int:
    """Claim and process one bounded batch of queued/retryable jobs.

    Each job gets its own transaction boundary. Processor exceptions are
    persisted as retry state; explicit permanent failures go directly to the
    dead-letter state without consuming the retry budget.
    """
    jobs = claim_retryable_jobs(db, now=now, limit=limit)
    processed = 0

    for job in jobs:
        try:
            mark_job_running(job, worker_id, now=now)
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Failed claiming crawl job %s", job.id)
            continue

        try:
            http_status, content_hash = processor(job)
            mark_job_success(
                job,
                http_status=http_status,
                content_hash=content_hash,
                now=now,
            )
            db.commit()
            processed += 1
        except Exception as exc:
            db.rollback()
            refreshed = db.query(CrawlJob).filter(CrawlJob.id == job.id).first()
            if refreshed is None:
                logger.error("Crawl job %s disappeared while processing", job.id)
                continue
            try:
                retryable = not isinstance(exc, CrawlJobError) or exc.retryable
                mark_job_failure(
                    refreshed,
                    str(exc),
                    now=now,
                    retryable=retryable,
                )
                db.commit()
            except Exception:
                db.rollback()
                logger.exception("Failed persisting failure state for crawl job %s", job.id)

    return processed
