"""Which promotions count as "live" for the dashboard and statistics."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import and_, or_

from app.core.config import settings
from app.models.promotion import Promotion


def live_promotion_filter(now: datetime, *, recency_days: int):
    """SQL condition for promotions worth showing to marketing.

    * ACTIVE promotions that have not passed their end date.
    * Promotions whose dates were not stated on the source (status UNKNOWN) are
      also shown while they keep being seen on a source, for a shorter window
      (UNDATED_PROMO_MAX_AGE_DAYS), because catalog pages often omit dates.
    """
    recent = Promotion.last_seen_at >= now - timedelta(days=recency_days)
    undated_cutoff = now - timedelta(days=min(recency_days, settings.UNDATED_PROMO_MAX_AGE_DAYS))
    dated_active = and_(
        Promotion.status == "ACTIVE",
        or_(Promotion.end_date.is_(None), Promotion.end_date >= now),
    )
    undated_recent = and_(
        Promotion.status == "UNKNOWN",
        Promotion.start_date.is_(None),
        Promotion.end_date.is_(None),
        Promotion.last_seen_at >= undated_cutoff,
    )
    return and_(recent, or_(dated_active, undated_recent))
