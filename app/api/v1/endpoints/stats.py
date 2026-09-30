from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db.session import get_db
from app.models.promotion import Promotion
from app.models.entity import Competitor, Brand, Retailer
from app.schemas.promotion import StatsResponse
from app.services.promotions.visibility import live_promotion_filter

router = APIRouter()


@router.get("/", response_model=StatsResponse)
def get_stats(db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    seven_days = now + timedelta(days=7)

    live = live_promotion_filter(now, recency_days=90)
    active_count = db.query(Promotion).filter(live).count()
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
        .filter(live)
        .group_by(Promotion.promotion_type)
        .all()
    )

    # By retailer
    ret_query = (
        db.query(Retailer.name, func.count(Promotion.id))
        .join(Promotion, Promotion.retailer_id == Retailer.id)
        .filter(live)
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


@router.get("/trends")
def get_trends(weeks: int = Query(8, ge=2, le=26), db: Session = Depends(get_db)):
    """New promotions and average discount per competitor per week (for the Insights page)."""
    now = datetime.now(timezone.utc)
    since = now - timedelta(weeks=weeks)
    week = func.date_trunc("week", Promotion.first_seen_at)
    rows = (
        db.query(Competitor.name, week.label("week"), func.count(Promotion.id), func.avg(Promotion.discount_percentage))
        .join(Promotion, Promotion.competitor_id == Competitor.id)
        .filter(Promotion.first_seen_at >= since)
        .group_by(Competitor.name, week)
        .all()
    )
    labels = []
    cursor = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    for i in range(weeks - 1, -1, -1):
        labels.append((cursor - timedelta(weeks=i)).strftime("%Y-%m-%d"))
    index = {label: i for i, label in enumerate(labels)}
    series = {}
    for name, wk, count, avg_disc in rows:
        label = wk.strftime("%Y-%m-%d")
        if label not in index:
            continue
        entry = series.setdefault(name, {"counts": [0] * weeks, "avg_discount": [None] * weeks, "total": 0})
        entry["counts"][index[label]] = count
        entry["avg_discount"][index[label]] = round(float(avg_disc), 1) if avg_disc is not None else None
        entry["total"] += count
    ordered = [{"competitor": n, **v} for n, v in sorted(series.items(), key=lambda kv: -kv[1]["total"])]
    return {"weeks": labels, "competitors": ordered}
