"""Shared builders for integration tests that insert promotions directly."""
import uuid
from datetime import datetime, timezone

from app.models.promotion import Promotion, PromotionEvidence
from app.models.source import SourceRegistry


def make_source(db, tag, *, approved=True, active=True, adapter="generic_catalog"):
    src = SourceRegistry(
        name=f"Test source {tag}", domain=f"src-{tag}.example", base_url=f"https://src-{tag}.example/promo-{uuid.uuid4().hex[:6]}",
        source_type="RETAILER", approval_status="APPROVED" if approved else "CANDIDATE", is_active=active, adapter_key=adapter,
    )
    db.add(src)
    db.flush()
    return src


def add_promotion(db, source, *, evidence=True, now=None, **fields):
    """A promotion that satisfies every eligibility gate unless a field says otherwise."""
    now = now or datetime.now(timezone.utc)
    base = dict(category="BISCUIT", promotion_type="DISCOUNT", status="ACTIVE", last_seen_at=now, last_verified_at=now,
                first_seen_at=now, rank_score=0.5, source_id=source.id if source else None)
    base.update(fields)
    promo = Promotion(**base)
    db.add(promo)
    db.flush()
    if evidence:
        db.add(PromotionEvidence(promotion_id=promo.id, evidence_text=f"evidence for {promo.product_name}",
                                 source_url="https://x.test/a", document_id=None))
        db.flush()
    return promo


def cleanup_source(db, source):
    from app.models.promotion_change import PromotionChangeEvent
    ids = [r[0] for r in db.query(Promotion.id).filter(Promotion.source_id == source.id).all()]
    if ids:
        db.query(PromotionChangeEvent).filter(PromotionChangeEvent.promotion_id.in_(ids)).delete(synchronize_session=False)
        db.query(PromotionEvidence).filter(PromotionEvidence.promotion_id.in_(ids)).delete(synchronize_session=False)
        db.query(Promotion).filter(Promotion.id.in_(ids)).delete(synchronize_session=False)
    db.query(SourceRegistry).filter(SourceRegistry.id == source.id).delete(synchronize_session=False)
