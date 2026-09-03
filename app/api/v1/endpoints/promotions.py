from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db.session import get_db
from app.models.promotion import Promotion, PromotionEvidence
from app.models.entity import Competitor, Brand, Retailer
from app.schemas.promotion import Top10Response, Top10PromotionItem, PromotionDetailOut, StatsResponse

router = APIRouter()


@router.get("/top10", response_model=Top10Response)
def get_top10_promotions(
    category: Optional[str] = Query(None, description="Filter by category (e.g. BISCUIT, CRACKER, WAFER)"),
    retailer: Optional[str] = Query(None, description="Filter by retailer name"),
    brand: Optional[str] = Query(None, description="Filter by brand name"),
    competitor: Optional[str] = Query(None, description="Filter by competitor name"),
    days: int = Query(90, description="Recency window in days (default 90 for 3-month rule)"),
    db: Session = Depends(get_db)
):
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)

    query = (
        db.query(Promotion)
        .outerjoin(Competitor, Promotion.competitor_id == Competitor.id)
        .outerjoin(Brand, Promotion.brand_id == Brand.id)
        .outerjoin(Retailer, Promotion.retailer_id == Retailer.id)
        .filter(
            Promotion.status == "ACTIVE",
            Promotion.last_seen_at >= cutoff,
            (Promotion.end_date == None) | (Promotion.end_date >= now)
        )
    )

    if category:
        query = query.filter(Promotion.category.ilike(f"%{category}%"))
    if retailer:
        query = query.filter(Retailer.name.ilike(f"%{retailer}%"))
    if brand:
        query = query.filter(Brand.name.ilike(f"%{brand}%"))
    if competitor:
        query = query.filter(Competitor.name.ilike(f"%{competitor}%"))

    # Order by rank_score DESC, then last_seen_at DESC
    results = query.order_by(Promotion.rank_score.desc(), Promotion.last_seen_at.desc()).limit(10).all()

    items = []
    for idx, p in enumerate(results, start=1):
        latest_evidence = (
            db.query(PromotionEvidence)
            .filter(PromotionEvidence.promotion_id == p.id)
            .order_by(PromotionEvidence.captured_at.desc())
            .first()
        )

        items.append(
            Top10PromotionItem(
                id=p.id,
                rank=idx,
                product_name=p.product_name,
                brand=p.brand.name if p.brand else None,
                competitor=p.competitor.name if p.competitor else None,
                category=p.category,
                pack_size=p.pack_size,
                retailer=p.retailer.name if p.retailer else None,
                channel=p.channel,
                promotion_type=p.promotion_type,
                buy_quantity=p.buy_quantity,
                free_quantity=p.free_quantity,
                regular_price=p.regular_price,
                promo_price=p.promo_price,
                discount_percentage=p.discount_percentage,
                effective_discount=p.discount_percentage,
                valid_until=p.end_date.strftime("%Y-%m-%d") if p.end_date else "Ongoing / Recent",
                rank_score=p.rank_score,
                ai_confidence=p.ai_confidence,
                source_reliability=p.source_reliability,
                evidence_quote=latest_evidence.evidence_text if latest_evidence else None,
                source_url=latest_evidence.source_url if latest_evidence else None,
                last_verified=p.last_seen_at
            )
        )

    return Top10Response(
        generated_at=now.isoformat(),
        count=len(items),
        promotions=items
    )


@router.get("/{promotion_id}", response_model=PromotionDetailOut)
def get_promotion_detail(promotion_id: str, db: Session = Depends(get_db)):
    p = db.query(Promotion).filter(Promotion.id == promotion_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Promotion not found")

    evidence = db.query(PromotionEvidence).filter(PromotionEvidence.promotion_id == p.id).all()
    return PromotionDetailOut(
        id=p.id,
        product_name=p.product_name,
        brand=p.brand.name if p.brand else None,
        competitor=p.competitor.name if p.competitor else None,
        category=p.category,
        pack_size=p.pack_size,
        retailer=p.retailer.name if p.retailer else None,
        channel=p.channel,
        promotion_type=p.promotion_type,
        buy_quantity=p.buy_quantity,
        free_quantity=p.free_quantity,
        regular_price=p.regular_price,
        promo_price=p.promo_price,
        discount_percentage=p.discount_percentage,
        start_date=p.start_date,
        end_date=p.end_date,
        status=p.status,
        source_reliability=p.source_reliability,
        ai_confidence=p.ai_confidence,
        rank_score=p.rank_score,
        first_seen_at=p.first_seen_at,
        last_seen_at=p.last_seen_at,
        evidence_items=evidence
    )
