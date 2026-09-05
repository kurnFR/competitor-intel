"""Durable CrawlJob state transitions and retry scheduling.

This module owns the database-independent state rules used by crawler workers.
Callers own transaction commit/rollback so a claimed job and its crawl result can
be committed atomically by the worker.
"""

from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.source import CrawlJob


QUEUED = "QUEUED"
RUNNING = "RUNNING"
RETRY_WAIT = "RETRY_WAIT"
SUCCESS = "SUCCESS"
DEAD_LETTER = "DEAD_LETTER"

DEFAULT_RETRY_BASE_SECONDS = 60
DEFAULT_RETRY_MAX_SECONDS = 3600


def _utc_now(value: Optional[datetime] = None) -> datetime:
    return value or datetime.now(timezone.utc)


def calculate_retry_delay(
    retry_count: int,
    base_seconds: int = DEFAULT_RETRY_BASE_SECONDS,
    max_seconds: int = DEFAULT_RETRY_MAX_SECONDS,
) -> int:
    """Return bounded exponential backoff for the next retry.

    retry_count is the number of failed attempts already recorded. The first
    retry therefore waits base_seconds, the second waits 2*base_seconds, etc.
    """
    if retry_count < 1:
        raise ValueError("retry_count must be >= 1")
    if base_seconds < 0 or max_seconds < 0:
        raise ValueError("retry delay bounds must be >= 0")
    return min(max_seconds, base_seconds * (2 ** (retry_count - 1)))


def mark_job_running(
    job: CrawlJob,
    worker_id: str,
    now: Optional[datetime] = None,
) -> CrawlJob:
    """Transition an eligible job to RUNNING."""
    if job.status not in {QUEUED, RETRY_WAIT}:
        raise ValueError(f"Cannot run job in status {job.status!r}")

    current = _utc_now(now)
    job.status = RUNNING
    job.started_at = job.started_at or current
    job.last_attempt_at = current
    job.next_retry_at = None
    job.worker_id = worker_id
    job.error_message = None
    return job


def mark_job_success(
    job: CrawlJob,
    http_status: Optional[int] = None,
    content_hash: Optional[str] = None,
    now: Optional[datetime] = None,
) -> CrawlJob:
    """Transition a running job to SUCCESS and clear retry state."""
    if job.status != RUNNING:
        raise ValueError(f"Cannot mark job successful from status {job.status!r}")

    current = _utc_now(now)
    job.status = SUCCESS
    job.completed_at = current
    job.last_attempt_at = current
    job.next_retry_at = None
    job.error_message = None
    if http_status is not None:
        job.http_status = http_status
    if content_hash is not None:
        job.content_hash = content_hash
    return job


def mark_job_failure(
    job: CrawlJob,
    error_message: str,
    http_status: Optional[int] = None,
    now: Optional[datetime] = None,
    base_seconds: int = DEFAULT_RETRY_BASE_SECONDS,
    max_seconds: int = DEFAULT_RETRY_MAX_SECONDS,
    retryable: bool = True,
) -> CrawlJob:
    """Record a failed attempt and schedule a retry or dead-letter the job."""
    if job.status != RUNNING:
        raise ValueError(f"Cannot fail job from status {job.status!r}")

    current = _utc_now(now)
    job.last_attempt_at = current
    job.error_message = error_message
    if http_status is not None:
        job.http_status = http_status

    if not retryable:
        job.status = DEAD_LETTER
        job.next_retry_at = None
        job.completed_at = current
        return job

    job.retry_count = (job.retry_count or 0) + 1
    max_retries = max(0, job.max_retries or 0)
    if job.retry_count <= max_retries:
        delay = calculate_retry_delay(job.retry_count, base_seconds, max_seconds)
        job.status = RETRY_WAIT
        job.next_retry_at = current + timedelta(seconds=delay)
        job.completed_at = None
    else:
        job.status = DEAD_LETTER
        job.next_retry_at = None
        job.completed_at = current

    return job


def claim_retryable_jobs(
    db: Session,
    now: Optional[datetime] = None,
    limit: int = 10,
) -> List[CrawlJob]:
    """Claim queued/retry-wait jobs whose retry time has arrived.

    PostgreSQL row locking with SKIP LOCKED allows multiple workers to poll the
    same queue without claiming the same job. The transaction remains open so
    the caller can assign a worker id and commit the claim atomically.
    """
    if limit < 1:
        raise ValueError("limit must be >= 1")

    current = _utc_now(now)
    query = (
        db.query(CrawlJob)
        .filter(
            CrawlJob.status.in_([QUEUED, RETRY_WAIT]),
            (CrawlJob.next_retry_at.is_(None)) | (CrawlJob.next_retry_at <= current),
        )
        .order_by(CrawlJob.created_at.asc())
        .with_for_update(skip_locked=True)
        .limit(limit)
    )
    return query.all()


def get_job(db: Session, job_id: UUID) -> Optional[CrawlJob]:
    """Fetch one crawl job by id for worker orchestration."""
    return db.query(CrawlJob).filter(CrawlJob.id == job_id).first()
