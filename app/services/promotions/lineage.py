"""Conservative promotion lineage detection for material offer changes."""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.promotion import Promotion
from app.services.promotions.identity import source_identity_periods_compatible


def find_superseded_promotion(
    db: Session,
    *,
    product_id: Any,
    retailer_id: Any,
    source_fingerprint: str,
    source_period: dict[str, Any],
) -> Optional[Promotion]:
    """Find the most recent active offer that this newly-created offer replaces.

    Lineage is deliberately conservative: both canonical product and retailer
    IDs must be resolved, the previous offer must still be active, and the
    campaign periods must overlap. This prevents unrelated recurring campaigns
    from being chained merely because they share a product name.
    """
    if product_id is None or retailer_id is None:
        return None

    candidates = (
        db.query(Promotion)
        .filter(
            Promotion.product_id == product_id,
            Promotion.retailer_id == retailer_id,
            Promotion.status == "ACTIVE",
            Promotion.source_identity_fingerprint.isnot(None),
            Promotion.source_identity_fingerprint != source_fingerprint,
        )
        .order_by(Promotion.last_seen_at.desc())
        .all()
    )

    for candidate in candidates:
        if source_identity_periods_compatible(
            source_period,
            {"start_date": candidate.start_date, "end_date": candidate.end_date},
        ):
            return candidate
    return None
