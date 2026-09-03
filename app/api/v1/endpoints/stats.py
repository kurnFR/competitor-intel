from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db.session import get_db
from app.models.promotion import Promotion
from app.models.entity import Competitor, Brand, Retailer
from app.schemas.promotion import StatsResponse

router = APIRouter()


@router.get("/", response_model=StatsResponse)
def get_stats(db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    seven_days = now + timedelta(days=7)

    active_count = db.query(Promotion).filter(Promotion.status == "ACTIVE").count()
    comp_count = db.query(Competitor).filter(Competitor.is_active == True).count()
    brand_count = db.query(Brand).count()
    ret_count = db.query(Retailer).count()

    expiring_soon = (
        db.query(Promotion)
        .filter(
            Promotion.status == "ACTIVE",
            Promotion.end_date != None,
            Promotion.end_date <= seven_days,
            Promotion.end_date >= now
        )
        .count()
    )

    # By promotion type
    type_counts = dict(
        db.query(Promotion.promotion_type, func.count(Promotion.id))
        .filter(Promotion.status == "ACTIVE")
        .group_by(Promotion.promotion_type)
        .all()
    )

    # By retailer
    ret_query = (
        db.query(Retailer.name, func.count(Promotion.id))
        .join(Promotion, Promotion.retailer_id == Retailer.id)
        .filter(Promotion.status == "ACTIVE")
        .group_by(Retailer.name)
        .all()
    )
    ret_counts = dict(ret_query)

    return StatsResponse(
        active_promotions=active_count,
        competitors_tracked=comp_count,
        brands_tracked=brand_count,
        retailers_tracked=ret_count,
        expiring_soon_7days=expiring_soon,
        type_distribution=type_counts,
        retailer_distribution=ret_counts
    )
