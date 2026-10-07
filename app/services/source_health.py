"""How healthy is a source? One definition, used by the Admin page, the analyst view, the checklist and the alerts."""
from __future__ import annotations

from datetime import datetime, timedelta

STALE_AFTER = timedelta(days=3)


def compute_health(source, now: datetime) -> str:
    if source.approval_status == "CANDIDATE":
        return "AWAITING_APPROVAL"
    if source.approval_status == "REJECTED":
        return "REJECTED"
    if not source.is_active:
        return "DISABLED"
    if source.last_crawled_at is None:
        return "NEVER_SCANNED"
    if source.last_error_at and (source.last_success_at is None or source.last_error_at > source.last_success_at):
        return "FAILING"
    if source.last_success_at and now - source.last_success_at > STALE_AFTER:
        return "STALE"
    return "OK"
