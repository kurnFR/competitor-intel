"""Canonical promotion upsert and observation linkage.

This service is deliberately transaction-scoped: callers own the session and
commit/rollback boundary. Re-processing the same extracted promotion resolves
to the same canonical promotion and observation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.promotion import Promotion, PromotionObservation
from app.services.promotions.identity import IDENTITY_VERSION, promotion_identity_fingerprint


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _promotion_data(item: Any, resolved: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    resolved = resolved or {}
    return {
        "competitor_id": resolved.get("competitor_id"),
        "brand_id": resolved.get("brand_id"),
        "product_id": resolved.get("product_id"),
        "retailer_id": resolved.get("retailer_id"),
        "product_name": getattr(item, "product_name", None),
        "sku": getattr(item, "sku", None),
        "pack_size": getattr(item, "pack_size", None),
        "promotion_type": getattr(item, "promotion_type", None),
        "buy_quantity": getattr(item, "buy_quantity", None),
        "free_quantity": getattr(item, "free_quantity", None),
        "bundle_quantity": getattr(item, "bundle_quantity", None),
        "cashback_amount": getattr(item, "cashback_amount", None),
        "voucher_amount": getattr(item, "voucher_amount", None),
        "minimum_purchase_amount": getattr(item, "minimum_purchase_amount", None),
        "minimum_purchase_quantity": getattr(item, "minimum_purchase_quantity", None),
        "gift_description": getattr(item, "gift_description", None),
        "promo_price": getattr(item, "promo_price", None),
        "currency": getattr(item, "currency", "IDR"),
        "promotion_title": getattr(item, "promotion_title", None),
        "start_date": getattr(item, "start_date", None),
        "end_date": getattr(item, "end_date", None),
        "channel": getattr(item, "channel", None),
        "geography": getattr(item, "geography", "Indonesia"),
    }


def upsert_promotion_observation(
    db: Session,
    *,
    document_id,
    item: Any,
    resolved_entities: Optional[dict[str, Any]] = None,
    raw_text: Optional[str] = None,
    extracted_json: Optional[dict[str, Any]] = None,
    observed_at: Optional[datetime] = None,
) -> tuple[Promotion, PromotionObservation, bool]:
    """Create/link a canonical promotion and its observation idempotently.

    Returns (promotion, observation, created_promotion). A repeated extraction
    for the same document and promotion returns the existing observation.
    """
    data = _promotion_data(item, resolved_entities)
    fingerprint = promotion_identity_fingerprint(data)
    now = observed_at or _utc_now()

    promotion = (
        db.query(Promotion)
        .filter(
            Promotion.identity_fingerprint == fingerprint,
            Promotion.identity_version == IDENTITY_VERSION,
        )
        .one_or_none()
    )

    created = promotion is None
    if promotion is None:
        promotion = Promotion(
            product_name=data["product_name"],
            identity_fingerprint=fingerprint,
            identity_version=IDENTITY_VERSION,
            first_seen_at=now,
            last_seen_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(promotion)
        db.flush()

    for field in (
        "competitor_id", "brand_id", "product_id", "retailer_id", "product_name",
        "sku", "pack_size", "category", "regular_price", "promo_price", "currency",
        "discount_percentage", "promotion_type", "buy_quantity", "free_quantity",
        "bundle_quantity", "cashback_amount", "voucher_amount",
        "minimum_purchase_amount", "minimum_purchase_quantity", "gift_description",
        "promotion_title", "promotion_description", "start_date", "end_date",
        "channel", "geography",
    ):
        if hasattr(item, field):
            value = getattr(item, field)
            if value is not None:
                setattr(promotion, field, value)

    if resolved_entities:
        for field in ("competitor_id", "brand_id", "product_id", "retailer_id"):
            value = resolved_entities.get(field)
            if value is not None:
                setattr(promotion, field, value)

    promotion.last_seen_at = max(promotion.last_seen_at, now)
    promotion.updated_at = now

    observation = (
        db.query(PromotionObservation)
        .filter(
            PromotionObservation.document_id == document_id,
            PromotionObservation.promotion_id == promotion.id,
        )
        .one_or_none()
    )

    if observation is None:
        observation = PromotionObservation(
            document_id=document_id,
            promotion_id=promotion.id,
            raw_text=raw_text,
            extracted_json=extracted_json,
            ai_confidence=getattr(item, "confidence", None),
            observed_at=now,
            created_at=now,
        )
        db.add(observation)
        db.flush()
    else:
        # Preserve the original observation timestamp, but refresh extracted
        # payload/confidence when a document is explicitly reprocessed.
        if raw_text is not None:
            observation.raw_text = raw_text
        if extracted_json is not None:
            observation.extracted_json = extracted_json
        confidence = getattr(item, "confidence", None)
        if confidence is not None:
            observation.ai_confidence = confidence

    return promotion, observation, created
