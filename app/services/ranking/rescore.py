"""Recompute rank scores so freshness decays even when a page is not re-crawled."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.entity import Competitor
from app.models.promotion import Promotion
from app.models.promotion_change import PromotionChangeEvent
from app.services.ranking.scorer import PromotionScorer

CHANGE_IMPACT_WINDOW_DAYS = 7


def rescore_promotions(db: Session, *, now: Optional[datetime] = None) -> int:
    """Recalculate rank_score for live promotions. Returns the number updated."""
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=CHANGE_IMPACT_WINDOW_DAYS)

    promotions = db.query(Promotion).filter(Promotion.status.in_(["ACTIVE", "UNKNOWN"])).all()
    if not promotions:
        return 0

    ids = [p.id for p in promotions]
    impact_by_promo = dict(
        db.query(PromotionChangeEvent.promotion_id, func.max(PromotionChangeEvent.change_impact))
        .filter(PromotionChangeEvent.promotion_id.in_(ids), PromotionChangeEvent.observed_at >= since)
        .group_by(PromotionChangeEvent.promotion_id)
        .all()
    )
    competitor_ids = {p.competitor_id for p in promotions if p.competitor_id}
    importance = dict(
        db.query(Competitor.id, Competitor.importance_score).filter(Competitor.id.in_(competitor_ids)).all()
    ) if competitor_ids else {}

    updated = 0
    for p in promotions:
        score = PromotionScorer.compute_total_score(
            promotion_type=p.promotion_type,
            discount_percentage=p.discount_percentage,
            source_reliability=p.source_reliability,
            last_seen_at=p.last_verified_at or p.last_seen_at,   # freshness is about verification (PRD 14)
            category=p.category,
            competitor_importance=importance.get(p.competitor_id, 0.5),
            ai_confidence=p.ai_confidence,
            change_impact=float(impact_by_promo.get(p.id) or 0.0),
            dates_known=p.start_date is not None or p.end_date is not None,
            now=now,
        )
        if abs(score - (p.rank_score or 0.0)) > 1e-6:
            p.rank_score = score
            updated += 1
    return updated
