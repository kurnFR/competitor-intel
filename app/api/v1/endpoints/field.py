"""Evidence-backed field observations and reviewer decisions."""

import base64
import io
from PIL import Image
from datetime import date, datetime, time, timezone
from uuid import UUID
from zoneinfo import ZoneInfo
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, HttpUrl, ConfigDict, model_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.deps import Principal, require_role
from app.db.session import get_db
from app.models.entity import Competitor, Retailer
from app.models.promotion import Promotion, PromotionEvidence
from app.services.geography import normalize_region, identity_token
from app.services.promotions.identity import promotion_identity_fingerprint, promotion_source_identity_fingerprint, SOURCE_IDENTITY_VERSION
from app.services.validation.lifecycle import evaluate_lifecycle

router = APIRouter(dependencies=[Depends(require_role("ANALYST"))])
WIB = ZoneInfo("Asia/Jakarta")


class Observation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    product_name: str = Field(min_length=1, max_length=255)
    category: Literal["BISCUIT", "CRACKER", "COOKIE", "WAFER", "SNACK"]
    competitor_id: UUID
    retailer_id: UUID
    geography: str = Field(min_length=1, max_length=255)
    pack_size: str = Field(min_length=1, max_length=50)
    promotion_type: Literal["DISCOUNT", "BUY_X_GET_Y", "MEMBER_PRICE", "BUNDLE", "CASHBACK", "VOUCHER"] = "DISCOUNT"
    buy_quantity: int | None = Field(None, ge=1, le=1000)
    free_quantity: int | None = Field(None, ge=1, le=1000)
    previous_id: UUID | None = None
    photo: str | None = Field(None, max_length=4000000)
    regular_price: float | None = Field(None, gt=0, lt=10000000)
    promo_price: float = Field(gt=0, lt=10000000)
    evidence: str = Field(min_length=5, max_length=5000)
    source_url: HttpUrl | None = None
    observed_on: date
    starts: date | None = None
    ends: date | None = None

    @model_validator(mode="after")
    def dates(self):
        if self.observed_on > datetime.now(WIB).date() or (self.starts and self.ends and self.ends < self.starts):
            raise ValueError("Check observation and validity dates.")
        if self.photo:
            try:
                raw = base64.b64decode(self.photo, validate=True)
                with Image.open(io.BytesIO(raw)) as image:
                    if image.format not in {"JPEG", "PNG"} or image.width * image.height > 24000000:
                        raise ValueError()
                    image.verify()
            except (OSError, ValueError, Image.DecompressionBombError) as exc:
                raise ValueError("Use a JPEG or PNG up to 3 MB and 24 megapixels.") from exc
        if self.promotion_type == "BUY_X_GET_Y" and not (self.buy_quantity and self.free_quantity):
            raise ValueError("Enter paid and free quantities.")
        if self.regular_price and self.promo_price > self.regular_price:
            raise ValueError("Promotion price exceeds regular price.")
        return self


@router.get("/options")
def options(db: Session = Depends(get_db)):
    return {
        key: [{"id": row.id, "name": row.name} for row in db.query(model).order_by(model.name)]
        for key, model in (("competitors", Competitor), ("retailers", Retailer))
    }


@router.put("/{submission_id}")
def submit(submission_id: UUID, body: Observation, actor: Principal = Depends(require_role("ANALYST")), db: Session = Depends(get_db)):
    if not db.get(Competitor, body.competitor_id) or not db.get(Retailer, body.retailer_id):
        raise HTTPException(422, "Unknown competitor or retailer.")
    if body.previous_id:
        previous = (
            db.execute(
                text("""SELECT status,submitted_by FROM competitor_intel.field_submissions
                                      WHERE id=:id FOR UPDATE"""),
                {"id": body.previous_id},
            )
            .mappings()
            .first()
        )
        if not previous or previous["status"] != "CORRECTION" or previous["submitted_by"] != actor.user.id:
            raise HTTPException(409, "Only the original submitter can replace a returned observation.")
        child = db.execute(
            text("SELECT id FROM competitor_intel.field_submissions WHERE previous_id=:id"), {"id": body.previous_id}
        ).scalar()
        if child and child != submission_id:
            raise HTTPException(409, "A correction has already been submitted.")
    db.execute(
        text("""INSERT INTO competitor_intel.field_submissions(id,submitted_by,payload,previous_id)
                        VALUES (:id,:actor,CAST(:payload AS jsonb),:previous_id) ON CONFLICT(id) DO NOTHING"""),
        {"id": submission_id, "actor": actor.user.id, "payload": body.model_dump_json(), "previous_id": body.previous_id},
    )
    row = db.execute(text("SELECT * FROM competitor_intel.field_submissions WHERE id=:id"), {"id": submission_id}).mappings().one()
    if row["submitted_by"] != actor.user.id or row["payload"] != body.model_dump(mode="json"):
        raise HTTPException(409, "Submission reference already used.")
    db.commit()
    return {"id": submission_id, "status": row["status"]}


@router.get("/")
def submissions(db: Session = Depends(get_db)):
    return (
        db.execute(
            text("""SELECT f.id,f.review_note,f.previous_id,c.name AS competitor,r.name AS retailer,payload - 'photo' AS payload, payload->>'photo' IS NOT NULL AS has_photo,status,promotion_id FROM competitor_intel.field_submissions f
                              LEFT JOIN competitor_intel.competitors c ON c.id=CAST(payload->>'competitor_id' AS uuid)
                              LEFT JOIN competitor_intel.retailers r ON r.id=CAST(payload->>'retailer_id' AS uuid)
                              ORDER BY (status='PENDING') DESC,submitted_at DESC LIMIT 200""")
        )
        .mappings()
        .all()
    )


@router.post("/{submission_id}/{decision}")
def review(
    submission_id: UUID,
    decision: Literal["approve", "reject", "correct"],
    note: str = "",
    actor: Principal = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
):
    row = (
        db.execute(text("SELECT * FROM competitor_intel.field_submissions WHERE id=:id FOR UPDATE"), {"id": submission_id})
        .mappings()
        .first()
    )
    if row is None:
        raise HTTPException(404, "Unknown submission.")
    if row["submitted_by"] == actor.user.id:
        raise HTTPException(403, "Another reviewer must decide this observation.")
    if len(note) > 500 or (decision == "correct" and not note.strip()):
        raise HTTPException(422, "Enter a correction reason of up to 500 characters.")
    status = {"approve": "APPROVED", "reject": "REJECTED", "correct": "CORRECTION"}[decision]
    if row["status"] != "PENDING":
        if row["status"] != status:
            raise HTTPException(409, "Submission already decided.")
        return {"status": status, "promotion_id": row["promotion_id"]}
    promotion_id = None
    if decision == "approve":
        b = Observation.model_validate(row["payload"])
        start = datetime.combine(b.starts, time.min, WIB) if b.starts else None
        end = datetime.combine(b.ends, time.max, WIB) if b.ends else None
        observed = datetime.combine(b.observed_on, time.min, WIB)
        p = Promotion(
            **b.model_dump(
                include={
                    "product_name",
                    "category",
                    "competitor_id",
                    "retailer_id",
                    "geography",
                    "pack_size",
                    "regular_price",
                    "promo_price",
                    "promotion_type",
                    "buy_quantity",
                    "free_quantity",
                }
            ),
            geography_region=normalize_region(b.geography),
            start_date=start,
            end_date=end,
            last_verified_at=observed,
            last_seen_at=observed,
            status=evaluate_lifecycle(start, end),
            ai_confidence=None,
        )
        identity = {
            **b.model_dump(),
            "promotion_type": p.promotion_type,
            "currency": "IDR",
            "start_date": start,
            "end_date": end,
            "geography": identity_token(b.geography),
        }
        fingerprint = promotion_identity_fingerprint(identity)
        source_fingerprint = promotion_source_identity_fingerprint(
            {**identity, "competitor": db.get(Competitor, b.competitor_id).name, "retailer": db.get(Retailer, b.retailer_id).name}
        )
        db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:fp, 0))"), {"fp": source_fingerprint})
        existing = db.query(Promotion).filter_by(identity_fingerprint=fingerprint).with_for_update().first()
        if existing is None:
            candidates = (
                db.query(Promotion)
                .filter_by(
                    source_identity_fingerprint=source_fingerprint,
                    competitor_id=b.competitor_id,
                    retailer_id=b.retailer_id,
                    category=b.category,
                    promo_price=b.promo_price,
                    start_date=start,
                    end_date=end,
                )
                .with_for_update()
                .limit(2)
                .all()
            )
            if len(candidates) > 1:
                raise HTTPException(409, "Multiple matching offers. Resolve the duplicate before approving.")
            existing = next(iter(candidates), None)
        if existing:
            if existing.regular_price != b.regular_price or existing.category != b.category:
                raise HTTPException(409, "Existing offer disagrees with the submitted details.")
            p = existing
            if not p.last_verified_at or observed > p.last_verified_at:
                p.last_verified_at = observed
        else:
            p.identity_fingerprint = fingerprint
            p.identity_version = SOURCE_IDENTITY_VERSION
            p.source_identity_fingerprint = source_fingerprint
            db.add(p)
            db.flush()
            p.ai_confidence = None
        promotion_id = p.id
        db.add(
            PromotionEvidence(
                promotion_id=p.id,
                evidence_type="APPROVED_FIELD",
                evidence_text=b.evidence,
                captured_at=observed,
                source_url=str(b.source_url) if b.source_url else (f"/api/v1/stats/field-photo/{submission_id}" if b.photo else None),
            )
        )
    db.execute(
        text("""UPDATE competitor_intel.field_submissions SET status=:status,review_note=:note,reviewed_at=:now,
                       reviewed_by=:actor,promotion_id=:promo WHERE id=:id"""),
        {
            "id": submission_id,
            "status": status,
            "note": note,
            "now": datetime.now(timezone.utc),
            "actor": actor.user.id,
            "promo": promotion_id,
        },
    )
    db.commit()
    return {"status": status, "promotion_id": promotion_id}


class ResponseAction(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    action: str = Field(min_length=1, max_length=500)
    owner: str = Field(min_length=1, max_length=100)
    due: date
    status: Literal["OPEN", "IN_PROGRESS", "DONE"]


@router.post("/actions/{promotion_id}/record")
def record_action(
    promotion_id: UUID, body: ResponseAction, actor: Principal = Depends(require_role("ANALYST")), db: Session = Depends(get_db)
):
    from uuid import uuid4

    if db.get(Promotion, promotion_id) is None:
        raise HTTPException(404, "Unknown promotion.")
    db.execute(
        text("""INSERT INTO competitor_intel.marketing_actions(id,promotion_id,action,owner,due,status,recorded_by)
                       VALUES(:id,:promo,:action,:owner,:due,:status,:actor)"""),
        {**body.model_dump(), "id": uuid4(), "promo": promotion_id, "actor": actor.user.id},
    )
    db.commit()
    return {"status": body.status}
