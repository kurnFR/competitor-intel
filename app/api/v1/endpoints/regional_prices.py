from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from app.db.session import get_db
from app.models.promotion import PromotionPriceObservation
from app.models.geography import Geography
from app.models.entity import Retailer
from app.models.source import SourceRegistry
from app.schemas.regional_price import RegionalPriceOut

router = APIRouter()


@router.get("/", response_model=List[RegionalPriceOut])
def list_regional_prices(
    promotion_id: Optional[str] = Query(default=None),
    geography_id: Optional[str] = Query(default=None),
    retailer_id: Optional[str] = Query(default=None),
    channel: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    q = db.query(PromotionPriceObservation, Geography, Retailer, SourceRegistry).outerjoin(
        Geography, PromotionPriceObservation.geography_id == Geography.id
    ).outerjoin(
        Retailer, PromotionPriceObservation.retailer_id == Retailer.id
    ).join(
        SourceRegistry, PromotionPriceObservation.source_id == SourceRegistry.id
    ).order_by(PromotionPriceObservation.captured_at.desc())

    if promotion_id:
        q = q.filter(PromotionPriceObservation.promotion_id == promotion_id)
    if geography_id:
        q = q.filter(PromotionPriceObservation.geography_id == geography_id)
    if retailer_id:
        q = q.filter(PromotionPriceObservation.retailer_id == retailer_id)
    if channel:
        q = q.filter(PromotionPriceObservation.channel == channel)

    rows = []
    for price, geo, retailer, source in q.limit(500).all():
        rows.append(RegionalPriceOut(
            id=price.id,
            promotion_id=price.promotion_id,
            geography=geo.name if geo else None,
            geography_source_text=price.geography_source_text,
            retailer=retailer.name if retailer else None,
            channel=price.channel,
            regular_price=price.regular_price,
            promo_price=price.promo_price,
            currency=price.currency,
            minimum_purchase_quantity=price.minimum_purchase_quantity,
            minimum_purchase_amount=price.minimum_purchase_amount,
            captured_at=price.captured_at,
            last_verified_at=price.last_verified_at,
            evidence_text=price.evidence_text,
            source_url=price.source_url or source.base_url,
        ))
    return rows
