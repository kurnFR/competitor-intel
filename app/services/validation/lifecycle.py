from datetime import datetime, timezone
from typing import Optional


ACTIVE = "ACTIVE"
UPCOMING = "UPCOMING"
EXPIRED = "EXPIRED"
UNKNOWN = "UNKNOWN"


def evaluate_lifecycle(
    start_dt: Optional[datetime],
    end_dt: Optional[datetime],
    now: Optional[datetime] = None,
) -> str:
    """Return lifecycle from source-provided dates only.

    Missing dates are UNKNOWN rather than being inferred from crawl time.
    """
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    else:
        current = current.astimezone(timezone.utc)

    if start_dt is not None:
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)
        else:
            start_dt = start_dt.astimezone(timezone.utc)

    if end_dt is not None:
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)
        else:
            end_dt = end_dt.astimezone(timezone.utc)

    if start_dt is None and end_dt is None:
        return UNKNOWN
    if start_dt is not None and current < start_dt:
        return UPCOMING
    if end_dt is not None and current > end_dt:
        return EXPIRED
    return ACTIVE
