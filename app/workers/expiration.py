import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from app.models.promotion import Promotion

logger = logging.getLogger(__name__)


def run_expiration_check(db: Session) -> int:
    """
    Checks active promotions and transitions expired ones:
    - If end_date < now -> EXPIRED
    - If end_date is null and last_seen_at > 7 days ago -> UNKNOWN
    """
    now = datetime.now(timezone.utc)
    seven_days_ago = now - timedelta(days=7)

    # 1. Past end date
    expired_query = (
        db.query(Promotion)
        .filter(
            Promotion.status == "ACTIVE",
            Promotion.end_date != None,
            Promotion.end_date < now
        )
    )
    count_expired = 0
    for p in expired_query.all():
        p.status = "EXPIRED"
        p.updated_at = now
        count_expired += 1

    # 2. Stale without end date
    stale_query = (
        db.query(Promotion)
        .filter(
            Promotion.status == "ACTIVE",
            Promotion.end_date == None,
            Promotion.last_seen_at < seven_days_ago
        )
    )
    count_stale = 0
    for p in stale_query.all():
        p.status = "UNKNOWN"
        p.updated_at = now
        count_stale += 1

    db.commit()
    logger.info(f"Expiration worker processed: {count_expired} marked EXPIRED, {count_stale} marked UNKNOWN.")
    return count_expired + count_stale
