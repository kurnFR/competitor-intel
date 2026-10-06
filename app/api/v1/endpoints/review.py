"""Review queue: confirm or reject uncertain entity matches found by the pipeline."""
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import Principal, client_ip, require_role
from app.db.session import get_db
from app.models.entity import Brand, Competitor, Product, Retailer
from app.models.promotion import Promotion
from app.models.resolution import ReviewQueue
from app.models.promotion import PromotionObservation
from app.services import auth as auth_service
from app.services.promotions.upsert import apply_observation_values

router = APIRouter()

# entity_type -> (model, Promotion foreign-key attribute)
ENTITY_MODELS = {
    "BRAND": (Brand, "brand_id"),
    "COMPETITOR": (Competitor, "competitor_id"),
    "RETAILER": (Retailer, "retailer_id"),
    "PRODUCT": (Product, "product_id"),
}


class ReviewItemOut(BaseModel):
    id: UUID
    entity_type: str
    reason: str
    confidence: Optional[float]
    priority: int
    status: str
    created_at: datetime
    promotion_id: Optional[UUID]
    promotion_product: Optional[str] = None
    promotion_competitor: Optional[str] = None
    current_match: Optional[str] = None
    suggested_match: Optional[str] = None
    can_approve: bool = False


class ResolveIn(BaseModel):
    decision: str = Field(pattern="^(APPROVED|REJECTED)$")
    notes: Optional[str] = Field(default=None, max_length=1000)


def _name(db: Session, entity_type: str, entity_id) -> Optional[str]:
    spec = ENTITY_MODELS.get((entity_type or "").upper())
    if not spec or not entity_id:
        return None
    row = db.get(spec[0], entity_id)
    return getattr(row, "name", None) if row else None


@router.get("/", response_model=List[ReviewItemOut])
def list_review_items(status: str = Query("PENDING", pattern="^(PENDING|APPROVED|REJECTED)$"),
                      limit: int = Query(50, ge=1, le=200),
                      _: Principal = Depends(require_role("ANALYST")), db: Session = Depends(get_db)):
    items = (db.query(ReviewQueue).filter(ReviewQueue.status == status)
             .order_by(ReviewQueue.priority.desc(), ReviewQueue.created_at.desc()).limit(limit).all())
    out = []
    for item in items:
        promo = db.get(Promotion, item.promotion_id) if item.promotion_id else None
        spec = ENTITY_MODELS.get((item.entity_type or "").upper())
        out.append(ReviewItemOut(
            id=item.id, entity_type=item.entity_type, reason=item.reason, confidence=item.confidence,
            priority=item.priority, status=item.status, created_at=item.created_at, promotion_id=item.promotion_id,
            promotion_product=promo.product_name if promo else None,
            promotion_competitor=promo.competitor.name if promo and promo.competitor else None,
            current_match=_name(db, item.entity_type, item.entity_id),
            suggested_match=_name(db, item.entity_type, item.candidate_entity_id),
            can_approve=bool(promo and item.observation_id) if item.entity_type == "CONFLICT" else bool(spec and promo and item.candidate_entity_id),
        ))
    return out


@router.post("/{item_id}/resolve", response_model=ReviewItemOut)
def resolve_review_item(item_id: UUID, body: ResolveIn, request: Request,
                        principal: Principal = Depends(require_role("ANALYST")), db: Session = Depends(get_db)):
    item = db.get(ReviewQueue, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Review item not found.")
    if item.status != "PENDING":
        raise HTTPException(status_code=409, detail="This item was already reviewed.")

    if item.entity_type == "CONFLICT":
        return _resolve_conflict(db, item, body, request, principal)

    if body.decision == "APPROVED":
        spec = ENTITY_MODELS.get((item.entity_type or "").upper())
        promo = db.get(Promotion, item.promotion_id) if item.promotion_id else None
        if not (spec and promo and item.candidate_entity_id):
            raise HTTPException(status_code=422, detail="There is no suggested match to approve; reject it instead.")
        setattr(promo, spec[1], item.candidate_entity_id)  # link the promotion to the confirmed entity

    item.status = body.decision
    item.review_notes = body.notes
    item.assigned_to = principal.user.username
    item.reviewed_at = datetime.now(timezone.utc)
    auth_service.audit(db, "review_resolved", username=principal.user.username, ip=client_ip(request),
                       detail={"item": str(item.id), "decision": body.decision, "entity_type": item.entity_type})
    db.commit()
    promo = db.get(Promotion, item.promotion_id) if item.promotion_id else None
    return ReviewItemOut(
        id=item.id, entity_type=item.entity_type, reason=item.reason, confidence=item.confidence,
        priority=item.priority, status=item.status, created_at=item.created_at, promotion_id=item.promotion_id,
        promotion_product=promo.product_name if promo else None,
        promotion_competitor=promo.competitor.name if promo and promo.competitor else None,
        current_match=_name(db, item.entity_type, item.entity_id),
        suggested_match=_name(db, item.entity_type, item.candidate_entity_id),
    )


def _resolve_conflict(db: Session, item: ReviewQueue, body: ResolveIn, request: Request, principal: Principal):
    """APPROVED = use the new source's values; REJECTED = keep the current values. Both observations stay on record."""
    promo = db.get(Promotion, item.promotion_id) if item.promotion_id else None
    if promo is None:
        raise HTTPException(status_code=422, detail="The promotion no longer exists.")
    if body.decision == "APPROVED":
        observation = db.get(PromotionObservation, item.observation_id) if item.observation_id else None
        if observation is None:
            raise HTTPException(status_code=422, detail="The conflicting observation is no longer available; keep the current values instead.")
        try:
            apply_observation_values(db, promo, observation)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
    item.status = body.decision
    item.review_notes = body.notes
    item.assigned_to = principal.user.username
    item.reviewed_at = datetime.now(timezone.utc)
    db.flush()
    still_open = db.query(ReviewQueue).filter(
        ReviewQueue.entity_type == "CONFLICT", ReviewQueue.promotion_id == promo.id, ReviewQueue.status == "PENDING").count()
    promo.has_open_conflict = still_open > 0
    auth_service.audit(db, "conflict_resolved", username=principal.user.username, ip=client_ip(request),
                       detail={"item": str(item.id), "promotion": str(promo.id),
                               "decision": "used_new_values" if body.decision == "APPROVED" else "kept_current_values"})
    db.commit()
    return ReviewItemOut(
        id=item.id, entity_type=item.entity_type, reason=item.reason, confidence=item.confidence, priority=item.priority,
        status=item.status, created_at=item.created_at, promotion_id=item.promotion_id, promotion_product=promo.product_name,
        promotion_competitor=promo.competitor.name if promo.competitor else None)
