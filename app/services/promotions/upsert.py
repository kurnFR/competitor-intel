"""Canonical promotion upsert, observation linkage, evidence, and lifecycle."""

from __future__ import annotations

import logging

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.promotion import Promotion, PromotionEvidence, PromotionObservation
from app.services.promotions.change_detection import detect_promotion_changes
from app.services.promotions.change_history import persist_promotion_change_events
from app.models.resolution import ReviewQueue
from app.models.source import CrawlDocument, SourceRegistry
from app.services.promotions.conflicts import APPLY, KEEP, REVIEW, arbitrate, describe
from app.services.geography import clean_wording, identity_token, normalize_region
from app.services.promotions.identity import (
    IDENTITY_VERSION,
    SOURCE_IDENTITY_VERSION,
    promotion_identity_fingerprint,
    promotion_source_identity_fingerprint,
    source_identity_periods_compatible,
)
from app.services.promotions.lineage import find_superseded_promotion
from app.services.ranking.scorer import PromotionScorer
from app.services.validation.lifecycle import evaluate_lifecycle
from app.services.validation.validator import PromotionValidator


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _promotion_data(item: Any, resolved: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    resolved = resolved or {}
    return {
        "competitor_id": resolved.get("competitor_id"), "brand_id": resolved.get("brand_id"), "product_id": resolved.get("product_id"), "retailer_id": resolved.get("retailer_id"),
        "product_name": getattr(item, "product_name", None), "sku": getattr(item, "sku", None), "pack_size": getattr(item, "pack_size", None), "promotion_type": getattr(item, "promotion_type", None),
        "buy_quantity": getattr(item, "buy_quantity", None), "free_quantity": getattr(item, "free_quantity", None), "bundle_quantity": getattr(item, "bundle_quantity", None), "cashback_amount": getattr(item, "cashback_amount", None),
        "voucher_amount": getattr(item, "voucher_amount", None), "minimum_purchase_amount": getattr(item, "minimum_purchase_amount", None), "minimum_purchase_quantity": getattr(item, "minimum_purchase_quantity", None),
        "gift_description": getattr(item, "gift_description", None), "promo_price": getattr(item, "promo_price", None), "currency": getattr(item, "currency", "IDR"), "promotion_title": getattr(item, "promotion_title", None),
        "start_date": getattr(item, "start_date", None), "end_date": getattr(item, "end_date", None), "channel": getattr(item, "channel", None), "geography": identity_token(getattr(item, "geography", None)),
    }


def _source_identity_data(item: Any) -> dict[str, Any]:
    return {
        "retailer": getattr(item, "retailer", None), "brand": getattr(item, "brand", None), "competitor": getattr(item, "competitor", None), "product_name": getattr(item, "product_name", None),
        "sku": getattr(item, "sku", None), "pack_size": getattr(item, "pack_size", None), "promotion_type": getattr(item, "promotion_type", None), "buy_quantity": getattr(item, "buy_quantity", None),
        "free_quantity": getattr(item, "free_quantity", None), "bundle_quantity": getattr(item, "bundle_quantity", None), "cashback_amount": getattr(item, "cashback_amount", None), "voucher_amount": getattr(item, "voucher_amount", None),
        "minimum_purchase_amount": getattr(item, "minimum_purchase_amount", None), "minimum_purchase_quantity": getattr(item, "minimum_purchase_quantity", None), "gift_description": getattr(item, "gift_description", None), "promo_price": getattr(item, "promo_price", None),
        "currency": getattr(item, "currency", "IDR"), "channel": getattr(item, "channel", None), "geography": identity_token(getattr(item, "geography", None)), "start_date": getattr(item, "start_date", None), "end_date": getattr(item, "end_date", None),
    }


def _persist_evidence(db: Session, *, promotion: Promotion, document_id, item: Any, source_url: Optional[str] = None, captured_at: Optional[datetime] = None) -> Optional[PromotionEvidence]:
    evidence_text = getattr(item, "evidence_quote", None)
    if not evidence_text or not str(evidence_text).strip():
        return None
    evidence_text = str(evidence_text).strip()
    existing = (db.query(PromotionEvidence).filter(
        PromotionEvidence.promotion_id == promotion.id, PromotionEvidence.document_id == document_id, PromotionEvidence.evidence_text == evidence_text,
    ).one_or_none())
    if existing is not None:
        return existing
    evidence = PromotionEvidence(
        promotion_id=promotion.id, document_id=document_id, evidence_type="TEXT", evidence_text=evidence_text,
        source_url=source_url, captured_at=captured_at or _utc_now(),
    )
    db.add(evidence)
    db.flush()
    return evidence


logger = logging.getLogger(__name__)

_REFRESHABLE_FIELDS = (
    "competitor_id", "brand_id", "product_id", "retailer_id", "product_name", "sku", "pack_size", "category", "regular_price", "promo_price", "currency", "discount_percentage", "promotion_type",
    "buy_quantity", "free_quantity", "bundle_quantity", "cashback_amount", "voucher_amount", "minimum_purchase_amount", "minimum_purchase_quantity", "gift_description", "promotion_title",
    "promotion_description", "channel", "geography",
)


def _refresh_canonical_fields(promotion: Promotion, item: Any) -> None:
    """Apply only explicit, validated source values; never let omissions erase data."""
    for field in _REFRESHABLE_FIELDS:
        if not hasattr(item, field):
            continue
        value = getattr(item, field)
        if value is not None:
            setattr(promotion, field, value)


def upsert_promotion_observation(db: Session, *, document_id, item: Any, resolved_entities: Optional[dict[str, Any]] = None, raw_text: Optional[str] = None, extracted_json: Optional[dict[str, Any]] = None, observed_at: Optional[datetime] = None, source_url: Optional[str] = None, extraction_metadata: Optional[dict[str, Any]] = None, source_reliability: float = 0.85, source_id=None) -> tuple[Promotion, PromotionObservation, bool]:
    """Validate, canonicalize, rank, and upsert a promotion observation."""
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
    if extracted_json is None and hasattr(item, "model_dump"):
        extracted_json = item.model_dump(mode="json")      # always keep what was extracted, so a conflict can be resolved later

    promotion = (db.query(Promotion).filter(
        Promotion.identity_fingerprint == fingerprint,
        Promotion.identity_version.in_([IDENTITY_VERSION, SOURCE_IDENTITY_VERSION]),
    ).one_or_none())
    def _match_by_source_fingerprint(fp: str):
        candidates = (db.query(Promotion).filter(
            Promotion.source_identity_fingerprint == fp, Promotion.identity_version == SOURCE_IDENTITY_VERSION,
        ).order_by(Promotion.last_seen_at.desc()).all())
        for candidate in candidates:
            if source_identity_periods_compatible(source_data, {"start_date": candidate.start_date, "end_date": candidate.end_date}):
                return candidate
        return None

    if promotion is None:
        promotion = _match_by_source_fingerprint(source_fingerprint)
    if promotion is None and source_data.get("geography") is None:
        # Promotions stored before geography became honest carry the fabricated default "Indonesia" in their
        # identity hash. Recognise them so an upgrade does not duplicate every promotion; the match below
        # re-stamps them with the new fingerprint.
        promotion = _match_by_source_fingerprint(promotion_source_identity_fingerprint({**source_data, "geography": "Indonesia"}))

    created = promotion is None
    superseded_promotion = None
    if promotion is None:
        promotion = Promotion(
            product_name=data["product_name"], identity_fingerprint=fingerprint, identity_version=SOURCE_IDENTITY_VERSION,
            source_identity_fingerprint=source_fingerprint, first_seen_at=now, last_seen_at=now, last_verified_at=now, created_at=now, updated_at=now,
        )
        db.add(promotion)
        db.flush()
        changes: list[dict[str, Any]] = []
        previous_source_id = None
        superseded_promotion = find_superseded_promotion(
            db,
            product_id=(resolved_entities or {}).get("product_id"),
            retailer_id=(resolved_entities or {}).get("retailer_id"),
            source_fingerprint=source_fingerprint,
            source_period=source_data,
        )
        if superseded_promotion is not None:
            promotion.supersedes_promotion_id = superseded_promotion.id
            superseded_promotion.status = "SUPERSEDED"
            superseded_promotion.updated_at = now
        verdict, conflict_changes, conflict_reason = APPLY, [], ""
    else:
        changes = detect_promotion_changes(promotion, item)
        promotion.source_identity_fingerprint = source_fingerprint
        promotion.identity_version = SOURCE_IDENTITY_VERSION
        # PRD 16: a different source disagreeing materially must not silently overwrite what we hold.
        previous_source_id = promotion.source_id
        verdict, conflict_changes, conflict_reason = arbitrate(
            db, promotion, changes, new_source_id=source_id, new_reliability=source_reliability, now=now)
        if verdict != APPLY:
            changes = []          # the stored values are not changing, so there is no change event

    applying = verdict == APPLY
    change_impact = PromotionScorer.calculate_change_impact(changes)
    if applying:
        _refresh_canonical_fields(promotion, item)
        if resolved_entities:
            for field in ("competitor_id", "brand_id", "product_id", "retailer_id"):
                value = resolved_entities.get(field)
                if value is not None:
                    setattr(promotion, field, value)

        if start_dt is not None:
            promotion.start_date = start_dt
        if end_dt is not None:
            promotion.end_date = end_dt

        if effective_discount is not None:
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
        competitor_importance=competitor_importance, ai_confidence=promotion.ai_confidence, change_impact=change_impact,
        dates_known=promotion.start_date is not None or promotion.end_date is not None,
    )
    promotion.last_seen_at = max(promotion.last_seen_at, now)
    if applying:
        # Facts passed validation and evidence checks against a freshly collected source (PRD 15).
        promotion.last_verified_at = max(promotion.last_verified_at or now, now)
        if source_id is not None:
            promotion.source_id = source_id
    promotion.geography = clean_wording(promotion.geography)
    promotion.geography_region = normalize_region(promotion.geography)
    promotion.updated_at = now

    observation = (db.query(PromotionObservation).filter(
        PromotionObservation.document_id == document_id, PromotionObservation.promotion_id == promotion.id,
    ).one_or_none())
    if observation is None:
        observation = PromotionObservation(
            document_id=document_id, promotion_id=promotion.id, raw_text=raw_text, extracted_json=extracted_json,
            ai_confidence=getattr(item, "confidence", None), extraction_model=metadata.get("model"), extraction_status=metadata.get("status"),
            extracted_at=metadata.get("extracted_at"), extraction_raw_response_hash=metadata.get("raw_response_hash"), extraction_rejected_count=metadata.get("rejected_count"), observed_at=now, created_at=now,
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

    if verdict == REVIEW:
        _open_conflict(db, promotion, observation, conflict_changes, conflict_reason, previous_source_id, source_id)
    elif verdict == KEEP:
        logger.info("Kept current values for promotion %s: %s", promotion.id, conflict_reason)

    persist_promotion_change_events(
        db,
        promotion=promotion,
        observation=observation,
        changes=changes,
        created=created,
        observed_at=now,
        document_id=document_id,
        change_impact=change_impact,
        superseded_promotion=superseded_promotion,
    )
    _persist_evidence(db, promotion=promotion, document_id=document_id, item=item, source_url=source_url, captured_at=now)
    return promotion, observation, created


def _source_name(db: Session, source_id) -> str:
    source = db.get(SourceRegistry, source_id) if source_id else None
    return source.name if source else "unknown source"


def _open_conflict(db: Session, promotion: Promotion, observation: PromotionObservation, material, reason: str,
                   current_source_id, new_source_id) -> None:
    """Freeze the stored values, hide the promotion from the Top 10 and ask a person to decide."""
    promotion.has_open_conflict = True
    text = describe(material, current_source=_source_name(db, current_source_id),
                    new_source=_source_name(db, new_source_id), reason=reason)
    # The same disagreement seen again (for example after a re-crawl of a slightly changed page) updates the one open item
    # to point at the freshest observation instead of piling up duplicates.
    existing = db.query(ReviewQueue).filter(
        ReviewQueue.entity_type == "CONFLICT", ReviewQueue.promotion_id == promotion.id,
        ReviewQueue.status == "PENDING", ReviewQueue.reason == text).first()
    if existing is not None:
        existing.observation_id = observation.id
    else:
        db.add(ReviewQueue(entity_type="CONFLICT", promotion_id=promotion.id, observation_id=observation.id,
                           priority=5, status="PENDING", reason=text))
    db.flush()


def apply_observation_values(db: Session, promotion: Promotion, observation: PromotionObservation) -> None:
    """Resolution 'use the new values': re-apply a stored observation's validated values to the promotion."""
    from app.schemas.ai import ExtractedPromotionItem

    wanted = {k: v for k, v in (observation.extracted_json or {}).items() if k in ExtractedPromotionItem.model_fields}
    item = ExtractedPromotionItem(**wanted)
    ok, reason, start_dt, end_dt, effective_discount = PromotionValidator.validate_and_normalize(item)
    if not ok:
        raise ValueError(f"The stored observation is no longer valid: {reason}")
    now = _utc_now()
    _refresh_canonical_fields(promotion, item)
    if start_dt is not None:
        promotion.start_date = start_dt
    if end_dt is not None:
        promotion.end_date = end_dt
    if effective_discount is not None:
        promotion.discount_percentage = effective_discount
    promotion.status = evaluate_lifecycle(promotion.start_date, promotion.end_date, now=now)
    document = db.get(CrawlDocument, observation.document_id) if observation.document_id else None
    if document is not None:
        promotion.source_id = document.source_id
    promotion.geography = clean_wording(promotion.geography)
    promotion.geography_region = normalize_region(promotion.geography)
    promotion.last_verified_at = now
    promotion.updated_at = now
