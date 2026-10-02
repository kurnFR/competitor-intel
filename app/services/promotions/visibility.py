"""Which promotions count as "live" and eligible for the dashboard, Top 10, exports and statistics (PRD 13-14)."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import and_, exists, func, or_

from app.models.promotion import Promotion, PromotionEvidence
from app.models.source import SourceRegistry


def live_promotion_filter(now: datetime, *, recency_days: int):
    """SQL condition for promotions eligible to be shown to marketing.

    A promotion must be:
    * commercially active: ACTIVE and not past its end date, or UNKNOWN with no dates stated (flagged in the UI);
    * recently VERIFIED (last_verified_at, not merely seen) within the freshness window;
    * backed by stored evidence text;
    * from a source that is approved and active.

    Whether an undated promotion is still listed is decided by the expiration worker (it becomes NOT_LISTED only
    when its source was successfully processed later and no longer lists it), not by a timer here.
    """
    verified_recently = Promotion.last_verified_at >= now - timedelta(days=recency_days)
    dated_active = and_(
        Promotion.status == "ACTIVE",
        or_(Promotion.end_date.is_(None), Promotion.end_date >= now),
    )
    undated = and_(Promotion.status == "UNKNOWN", Promotion.start_date.is_(None), Promotion.end_date.is_(None))
    has_evidence = exists().where(
        PromotionEvidence.promotion_id == Promotion.id,
        func.length(func.trim(PromotionEvidence.evidence_text)) > 0,
    )
    source_approved = exists().where(
        SourceRegistry.id == Promotion.source_id,
        SourceRegistry.is_active.is_(True),
        SourceRegistry.approval_status == "APPROVED",
    )
    return and_(verified_recently, or_(dated_active, undated), has_evidence, source_approved)
