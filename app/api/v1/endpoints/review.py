from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db.session import get_db
from app.models.promotion import Promotion, PromotionEvidence
from app.models.entity import Brand, Competitor, Retailer
from app.schemas.review import ReviewQueueItem, ReviewDecision, ReviewDecisionOut

router = APIRouter()


@router.get("/", response_model=list[ReviewQueueItem])
def list_review_queue(
    min_confidence: Optional[float] = Query(None, ge=0, le=1),
    category: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = (
        db.query(Promotion)
        .outerjoin(Brand, Promotion.brand_id == Brand.id)
        .outerjoin(Competitor, Promotion.competitor_id == Competitor.id)
        .outerjoin(Retailer, Promotion.retailer_id == Retailer.id)
        .filter(Promotion.status == "PENDING_REVIEW")
    )
    if min_confidence is not None:
        query = query.filter(Promotion.ai_confidence >= min_confidence)
    if category:
        query = query.filter(Promotion.category.ilike(f"%{category}%"))

    promotions = query.order_by(Promotion.ai_confidence.asc(), Promotion.last_seen_at.desc()).limit(limit).all()
    items = []
    for promotion in promotions:
        evidence = (
            db.query(PromotionEvidence)
            .filter(PromotionEvidence.promotion_id == promotion.id)
            .order_by(PromotionEvidence.captured_at.desc())
            .first()
        )
        items.append(
            ReviewQueueItem(
                id=promotion.id,
                product_name=promotion.product_name,
                brand=promotion.brand.name if promotion.brand else None,
                competitor=promotion.competitor.name if promotion.competitor else None,
                category=promotion.category,
                retailer=promotion.retailer.name if promotion.retailer else None,
                channel=promotion.channel,
                geography=promotion.legacy_geography,
                promotion_type=promotion.promotion_type,
                regular_price=promotion.regular_price,
                promo_price=promotion.promo_price,
                discount_percentage=promotion.discount_percentage,
                start_date=promotion.start_date,
                end_date=promotion.end_date,
                ai_confidence=promotion.ai_confidence,
                source_reliability=promotion.source_reliability,
                last_seen_at=promotion.last_seen_at,
                evidence_quote=evidence.evidence_text if evidence else None,
                source_url=evidence.source_url if evidence else None,
            )
        )
    return items


@router.post("/{promotion_id}/decision", response_model=ReviewDecisionOut)
def decide_review(
    promotion_id: str,
    decision: ReviewDecision,
    db: Session = Depends(get_db),
):
    normalized = decision.decision.upper()
    if normalized not in {"APPROVE", "REJECT"}:
        raise HTTPException(status_code=400, detail="decision must be APPROVE or REJECT")

    promotion = db.query(Promotion).filter(Promotion.id == promotion_id).first()
    if not promotion:
        raise HTTPException(status_code=404, detail="Promotion not found")
    if promotion.status not in {"PENDING_REVIEW", "ACTIVE", "REJECTED"}:
        raise HTTPException(status_code=409, detail=f"Promotion is not reviewable from status {promotion.status}")

    now = datetime.now(timezone.utc)
    if normalized == "APPROVE":
        promotion.status = "ACTIVE"
        promotion.last_verified_at = now
    else:
        promotion.status = "REJECTED"
        promotion.last_verified_at = None

    db.add(promotion)
    db.commit()
    db.refresh(promotion)
    return ReviewDecisionOut(
        id=promotion.id,
        status=promotion.status,
        reviewed_at=now,
        reason=decision.reason,
    )
