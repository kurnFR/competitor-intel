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


def score_inputs(db: Session, promotions, *, now: datetime) -> dict:
    """The inputs the score needs for each promotion (shared by rescoring and by the 'why this rank' explanation)."""
    if not promotions:
        return {}
    since = now - timedelta(days=CHANGE_IMPACT_WINDOW_DAYS)
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
    return {
        p.id: dict(
            promotion_type=p.promotion_type, discount_percentage=p.discount_percentage, source_reliability=p.source_reliability,
            last_seen_at=p.last_verified_at or p.last_seen_at,   # freshness is about verification (PRD 14)
            category=p.category, competitor_importance=importance.get(p.competitor_id, 0.5), ai_confidence=p.ai_confidence,
            change_impact=float(impact_by_promo.get(p.id) or 0.0), dates_known=p.start_date is not None or p.end_date is not None,
            now=now,
        )
        for p in promotions
    }


def explain_scores(db: Session, promotions, *, now: Optional[datetime] = None) -> dict:
    """promotion id -> score breakdown, with a plain-language note per component."""
    now = now or datetime.now(timezone.utc)
    out = {}
    inputs_by_id = score_inputs(db, list(promotions), now=now)
    for p in promotions:
        inputs = inputs_by_id[p.id]
        result = PromotionScorer.explain(**inputs)
        notes = {
            "strength": f"{p.promotion_type.replace('_', ' ').title()}" + (f", {p.discount_percentage:g}% off" if p.discount_percentage else ""),
            "reliability": f"Source reliability {round((p.source_reliability or 0) * 100)}%",
            "freshness": f"Verified {max(0, (now - (p.last_verified_at or p.last_seen_at)).days)} day(s) ago",
            "relevance": f"{(p.category or 'Other').title()} " + ("is a core category" if result["components"][3]["value"] == 1.0 else "is outside the core categories"),
            "importance": f"Competitor importance {inputs['competitor_importance']:g}",
            "confidence": f"AI extraction confidence {round((p.ai_confidence or 0) * 100)}%",
            "change": "A material change was seen in the last 7 days" if inputs["change_impact"] > 0 else "No recent change",
        }
        for c in result["components"]:
            c["note"] = notes[c["key"]]
        out[p.id] = result
    return out


def rescore_promotions(db: Session, *, now: Optional[datetime] = None) -> int:
    """Recalculate rank_score for live promotions. Returns the number updated."""
    now = now or datetime.now(timezone.utc)
    promotions = db.query(Promotion).filter(Promotion.status.in_(["ACTIVE", "UNKNOWN"])).all()
    inputs_by_id = score_inputs(db, promotions, now=now)
    updated = 0
    for p in promotions:
        score = PromotionScorer.compute_total_score(**inputs_by_id[p.id])
        if abs(score - (p.rank_score or 0.0)) > 1e-6:
            p.rank_score = score
            updated += 1
    return updated
