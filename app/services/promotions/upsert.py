"""Canonical promotion upsert, observation linkage, evidence, and lifecycle."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.promotion import Promotion, PromotionEvidence, PromotionObservation
from app.services.promotions.identity import (
    IDENTITY_VERSION,
    SOURCE_IDENTITY_VERSION,
    promotion_identity_fingerprint,
    promotion_source_identity_fingerprint,
    source_identity_periods_compatible,
)
from app.services.ranking.scorer import PromotionScorer
from app.services.validation.lifecycle import evaluate_lifecycle
from app.services.validation.validator import PromotionValidator


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _promotion_data(item: Any, resolved: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    resolved = resolved or {}
    return {
        "competitor_id": resolved.get("competitor_id"), "brand_id": resolved.get("brand_id"),
        "product_id": resolved.get("product_id"), "retailer_id": resolved.get("retailer_id"),
        "product_name": getattr(item, "product_name", None), "sku": getattr(item, "sku", None),
        "pack_size": getattr(item, "pack_size", None), "promotion_type": getattr(item, "promotion_type", None),
        "buy_quantity": getattr(item, "buy_quantity", None), "free_quantity": getattr(item, "free_quantity", None),
        "bundle_quantity": getattr(item, "bundle_quantity", None), "cashback_amount": getattr(item, "cashback_amount", None),
        "voucher_amount": getattr(item, "voucher_amount", None), "minimum_purchase_amount": getattr(item, "minimum_purchase_amount", None),
        "minimum_purchase_quantity": getattr(item, "minimum_purchase_quantity", None), "gift_description": getattr(item, "gift_description", None),
        "promo_price": getattr(item, "promo_price", None), "currency": getattr(item, "currency", "IDR"),
        "promotion_title": getattr(item, "promotion_title", None), "start_date": getattr(item, "start_date", None),
        "end_date": getattr(item, "end_date", None), "channel": getattr(item, "channel", None),
        "geography": getattr(item, "geography", "Indonesia"),
    }


def _source_identity_data(item: Any) -> dict[str, Any]:
    """Return source-observed values used by the stable commercial identity."""
    return {
        "retailer": getattr(item, "retailer", None), "brand": getattr(item, "brand", None),
        "competitor": getattr(item, "competitor", None), "product_name": getattr(item, "product_name", None),
        "sku": getattr(item, "sku", None), "pack_size": getattr(item, "pack_size", None),
        "promotion_type": getattr(item, "promotion_type", None), "buy_quantity": getattr(item, "buy_quantity", None),
        "free_quantity": getattr(item, "free_quantity", None), "bundle_quantity": getattr(item, "bundle_quantity", None),
        "cashback_amount": getattr(item, "cashback_amount", None), "voucher_amount": getattr(item, "voucher_amount", None),
        "minimum_purchase_amount": getattr(item, "minimum_purchase_amount", None),
        "minimum_purchase_quantity": getattr(item, "minimum_purchase_quantity", None),
        "gift_description": getattr(item, "gift_description", None), "promo_price": getattr(item, "promo_price", None),
        "currency": getattr(item, "currency", "IDR"), "channel": getattr(item, "channel", None),
        "geography": getattr(item, "geography", "Indonesia"), "start_date": getattr(item, "start_date", None),
        "end_date": getattr(item, "end_date", None),
    }


def _persist_evidence(db: Session, *, promotion: Promotion, document_id, item: Any,
                      source_url: Optional[str] = None, captured_at: Optional[datetime] = None) -> Optional[PromotionEvidence]:
    evidence_text = getattr(item, "evidence_quote", None)
    if not evidence_text or not str(evidence_text).strip():
        return None
    evidence_text = str(evidence_text).strip()
    existing = (db.query(PromotionEvidence).filter(
        PromotionEvidence.promotion_id == promotion.id,
        PromotionEvidence.document_id == document_id,
        PromotionEvidence.evidence_text == evidence_text,
    ).one_or_none())
    if existing is not None:
        return existing
    evidence = PromotionEvidence(
        promotion_id=promotion.id, document_id=document_id, evidence_type="TEXT",
        evidence_text=evidence_text, source_url=source_url, captured_at=captured_at or _utc_now(),
    )
    db.add(evidence)
    db.flush()
    return evidence


def upsert_promotion_observation(db: Session, *, document_id, item: Any,
                                 resolved_entities: Optional[dict[str, Any]] = None,
                                 raw_text: Optional[str] = None,
                                 extracted_json: Optional[dict[str, Any]] = None,
                                 observed_at: Optional[datetime] = None,
                                 source_url: Optional[str] = None,
                                 extraction_metadata: Optional[dict[str, Any]] = None,
                                 source_reliability: float = 0.85) -> tuple[Promotion, PromotionObservation, bool]:
    """Validate, canonicalize, rank, and upsert a promotion observation.

    The caller owns the transaction. v2 source identity prevents entity-ID or
    copy-text changes from fragmenting a campaign while period compatibility
    keeps non-overlapping recurring campaigns separate.
    """
    is_valid, reason, start_dt, end_dt, effective_discount = PromotionValidator.validate_and_normalize(item)
    if not is_valid:
        raise ValueError(f"Invalid promotion '{getattr(item, 'product_name', '')}': {reason}")
    evidence_valid, evidence_reason = PromotionValidator.validate_evidence_quote(item, raw_text)
    if not evidence_valid:
        raise ValueError(f"Unverifiable evidence for promotion '{getattr(item, 'product_name', '')}': {evidence_reason}")

    data = _promotion_data(item, resolved_entities)
    fingerprint = promotion_identity_fingerprint(data)
    source_data = _source_identity_data(item)
    source_fingerprint = promotion_source_identity_fingerprint(source_data)
    now = observed_at or _utc_now()
    metadata = extraction_metadata or {}

    promotion = (db.query(Promotion).filter(
        Promotion.identity_fingerprint == fingerprint,
        Promotion.identity_version == IDENTITY_VERSION,
    ).one_or_none())

    if promotion is None:
        source_candidates = (db.query(Promotion).filter(
            Promotion.source_identity_fingerprint == source_fingerprint,
            Promotion.identity_version == SOURCE_IDENTITY_VERSION,
        ).order_by(Promotion.last_seen_at.desc()).all())
        for candidate in source_candidates:
            if source_identity_periods_compatible(source_data, {
                "start_date": candidate.start_date, "end_date": candidate.end_date,
            }):
                promotion = candidate
                break

    created = promotion is None
    if promotion is None:
        promotion = Promotion(
            product_name=data["product_name"], identity_fingerprint=fingerprint,
            identity_version=SOURCE_IDENTITY_VERSION, source_identity_fingerprint=source_fingerprint,
            first_seen_at=now, last_seen_at=now, created_at=now, updated_at=now,
        )
        db.add(promotion)
        db.flush()
    else:
        promotion.source_identity_fingerprint = source_fingerprint
        promotion.identity_version = SOURCE_IDENTITY_VERSION

    # Only source-provided non-null values can improve canonical fields.
    # In particular, a later observation with missing dates must not erase
    # dates established by an earlier, stronger observation.
    for field in (
        "competitor_id", "brand_id", "product_id", "retailer_id", "product_name", "sku", "pack_size",
        "category", "regular_price", "promo_price", "currency", "discount_percentage", "promotion_type",
        "buy_quantity", "free_quantity", "bundle_quantity", "cashback_amount", "voucher_amount",
        "minimum_purchase_amount", "minimum_purchase_quantity", "gift_description", "promotion_title",
        "promotion_description", "channel", "geography",
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

    if start_dt is not None:
        promotion.start_date = start_dt
    if end_dt is not None:
        promotion.end_date = end_dt

    promotion.discount_percentage = effective_discount
    promotion.status = evaluate_lifecycle(promotion.start_date, promotion.end_date, now=now)
    promotion.source_reliability = max(promotion.source_reliability or 0.0, source_reliability)
    promotion.ai_confidence = max(promotion.ai_confidence or 0.0, getattr(item, "confidence", 0.0) or 0.0)
    competitor_importance = 0.5
    if resolved_entities and resolved_entities.get("competitor_importance") is not None:
        competitor_importance = float(resolved_entities["competitor_importance"])
    promotion.rank_score = PromotionScorer.compute_total_score(
        promotion_type=promotion.promotion_type, discount_percentage=promotion.discount_percentage,
        source_reliability=promotion.source_reliability, last_seen_at=now, category=promotion.category,
        competitor_importance=competitor_importance, ai_confidence=promotion.ai_confidence,
    )
    promotion.last_seen_at = max(promotion.last_seen_at, now)
    promotion.updated_at = now

    observation = (db.query(PromotionObservation).filter(
        PromotionObservation.document_id == document_id,
        PromotionObservation.promotion_id == promotion.id,
    ).one_or_none())
    if observation is None:
        observation = PromotionObservation(
            document_id=document_id, promotion_id=promotion.id, raw_text=raw_text,
            extracted_json=extracted_json, ai_confidence=getattr(item, "confidence", None),
            extraction_model=metadata.get("model"), extraction_status=metadata.get("status"),
            extracted_at=metadata.get("extracted_at"), extraction_raw_response_hash=metadata.get("raw_response_hash"),
            extraction_rejected_count=metadata.get("rejected_count"), observed_at=now, created_at=now,
        )
        db.add(observation)
        db.flush()
    else:
        if raw_text is not None: observation.raw_text = raw_text
        if extracted_json is not None: observation.extracted_json = extracted_json
        confidence = getattr(item, "confidence", None)
        if confidence is not None: observation.ai_confidence = confidence
        if metadata.get("model") is not None: observation.extraction_model = metadata["model"]
        if metadata.get("status") is not None: observation.extraction_status = metadata["status"]
        if metadata.get("extracted_at") is not None: observation.extracted_at = metadata["extracted_at"]
        if metadata.get("raw_response_hash") is not None: observation.extraction_raw_response_hash = metadata["raw_response_hash"]
        if metadata.get("rejected_count") is not None: observation.extraction_rejected_count = metadata["rejected_count"]

    _persist_evidence(db, promotion=promotion, document_id=document_id, item=item, source_url=source_url, captured_at=now)
    return promotion, observation, created
