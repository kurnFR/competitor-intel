"""Marketing-facing promotion change feed derived from observations."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.promotions.change_detection import detect_promotion_changes


def build_change_feed_item(promotion: Any, item: Any, *, observed_at: datetime | None = None) -> dict:
    observed_at = observed_at or datetime.now(timezone.utc)
    changes = detect_promotion_changes(promotion, item)
    return {
        "promotion_id": str(promotion.id),
        "observed_at": observed_at.isoformat(),
        "event_type": "CHANGED" if changes else "OBSERVED",
        "changes": changes,
        "competitor_id": str(promotion.competitor_id) if promotion.competitor_id else None,
        "brand_id": str(promotion.brand_id) if promotion.brand_id else None,
        "product_id": str(promotion.product_id) if promotion.product_id else None,
        "retailer_id": str(promotion.retailer_id) if promotion.retailer_id else None,
        "rank_score": promotion.rank_score,
        "ai_confidence": promotion.ai_confidence,
        "source_reliability": promotion.source_reliability,
    }
