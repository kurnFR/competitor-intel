import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.promotion import Promotion
from app.models.source import SourceRegistry
from app.services.validation.lifecycle import NOT_LISTED

logger = logging.getLogger(__name__)


def run_expiration_check(db: Session) -> int:
    """Move promotions out of the live set when the evidence says they are over.

    1. An explicit end date in the past -> EXPIRED (this overrides crawl freshness).
    2. An UPCOMING promotion whose start date has arrived -> ACTIVE.
    3. An ACTIVE promotion with a future start date -> UPCOMING.
    4. A promotion without an end date is NOT_LISTED only when its source was successfully collected and
       processed AFTER we last verified it (by more than UNDATED_PROMO_MAX_AGE_DAYS) and it was not found again.
       If the source has been failing or unreachable, nothing is concluded: a failed crawl is never read as
       "the source lists zero promotions" (PRD 5).
    5. Undated promotions without an associated source that are older than grace are also marked NOT_LISTED.
    """
    now = datetime.now(timezone.utc)

    count_expired = 0
    for p in db.query(Promotion).filter(
        Promotion.status.in_(["ACTIVE", "UNKNOWN", "UPCOMING"]),
        Promotion.end_date.isnot(None),
        Promotion.end_date < now,
    ).all():
        p.status = "EXPIRED"
        p.updated_at = now
        count_expired += 1

    # Transition UPCOMING to ACTIVE once their start date has arrived
    count_activated = 0
    for p in db.query(Promotion).filter(
        Promotion.status == "UPCOMING",
        Promotion.start_date.isnot(None),
        Promotion.start_date <= now,
        or_(Promotion.end_date.is_(None), Promotion.end_date >= now),
    ).all():
        p.status = "ACTIVE"
        p.updated_at = now
        count_activated += 1

    # Ensure ACTIVE promotions with a future start date are marked UPCOMING
    for p in db.query(Promotion).filter(
        Promotion.status == "ACTIVE",
        Promotion.start_date.isnot(None),
        Promotion.start_date > now,
    ).all():
        p.status = "UPCOMING"
        p.updated_at = now

    grace = timedelta(days=settings.UNDATED_PROMO_MAX_AGE_DAYS)
    count_unlisted = 0
    gone = (
        db.query(Promotion)
        .join(SourceRegistry, SourceRegistry.id == Promotion.source_id)
        .filter(
            Promotion.status.in_(["ACTIVE", "UNKNOWN"]),
            Promotion.end_date.is_(None),
            SourceRegistry.last_processed_at.isnot(None),
            SourceRegistry.last_processed_at > Promotion.last_verified_at + grace,
        )
    )
    for p in gone.all():
        p.status = NOT_LISTED
        p.updated_at = now
        count_unlisted += 1

    # Undated promotions without a source that are older than grace
    gone_no_source = (
        db.query(Promotion)
        .filter(
            Promotion.status.in_(["ACTIVE", "UNKNOWN"]),
            Promotion.end_date.is_(None),
            Promotion.source_id.is_(None),
            Promotion.last_verified_at < now - grace,
        )
    )
    for p in gone_no_source.all():
        p.status = NOT_LISTED
        p.updated_at = now
        count_unlisted += 1

    db.commit()
    logger.info(
        "Expiration worker: %d marked EXPIRED, %d marked NOT_LISTED, %d marked ACTIVE.",
        count_expired, count_unlisted, count_activated,
    )
    return count_expired + count_unlisted + count_activated
