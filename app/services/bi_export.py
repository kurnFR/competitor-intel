"""Automated Executive BI Feed Generator for Tableau, PowerBI, and Excel.

Transforms raw and structured promotion intelligence into a flattened, dimensional
analytical dataset with unit economics (price per 100g), campaign classifications,
and competitive positioning metrics.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session, contains_eager

from app.models.entity import Brand, Competitor, Retailer
from app.models.own_product import OwnProduct
from app.models.promotion import Promotion, PromotionEvidence
from app.services.campaigns import detect_campaign_tags
from app.services.comparison import effective_pack_price, parse_pack_grams, per_100g
from app.services.exporting import safe_cell
from app.services.promotions.visibility import live_promotion_filter

BI_FEED_COLUMNS = [
    "promotion_id",
    "product_name",
    "brand",
    "competitor",
    "category",
    "pack_size",
    "pack_grams",
    "regular_price",
    "promo_price",
    "effective_pack_price",
    "price_per_100g",
    "discount_percentage",
    "promotion_type",
    "campaign_codes",
    "campaign_labels",
    "retailer",
    "channel",
    "geography_region",
    "geography_raw",
    "start_date",
    "end_date",
    "dates_stated",
    "status",
    "is_active",
    "rank_score",
    "ai_confidence",
    "source_reliability",
    "has_conflict",
    "undercuts_our_product",
    "first_seen_at",
    "last_seen_at",
    "last_verified_at",
    "source_url",
    "evidence_quote",
]


def build_bi_feed(
    db: Session,
    *,
    category: Optional[str] = None,
    competitor_id: Optional[str] = None,
    retailer_name: Optional[str] = None,
    region: Optional[str] = None,
    campaign_code: Optional[str] = None,
    days: int = 90,
    active_only: bool = True,
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Build a dimensional analytical dataset suitable for Tableau/PowerBI ingestion."""
    now = now or datetime.now(timezone.utc)

    # Pre-fetch own products for undercut detection
    own_products = db.query(OwnProduct).filter(OwnProduct.is_active.is_(True)).all()
    own_by_cat: Dict[str, List[float]] = {}
    for own in own_products:
        grams = own.pack_grams or parse_pack_grams(own.pack_size)
        unit = per_100g(own.regular_price, grams)
        if unit is not None:
            own_by_cat.setdefault((own.category or "").upper(), []).append(unit)

    # Base query for promotions
    query = (
        db.query(Promotion)
        .outerjoin(Competitor, Promotion.competitor_id == Competitor.id)
        .outerjoin(Brand, Promotion.brand_id == Brand.id)
        .outerjoin(Retailer, Promotion.retailer_id == Retailer.id)
        .options(
            contains_eager(Promotion.competitor),
            contains_eager(Promotion.brand),
            contains_eager(Promotion.retailer),
        )
    )

    if active_only:
        query = query.filter(live_promotion_filter(now, recency_days=days))

    if category:
        query = query.filter(Promotion.category == category.upper())

    if competitor_id:
        try:
            cid = UUID(competitor_id)
            query = query.filter(Promotion.competitor_id == cid)
        except (ValueError, TypeError):
            query = query.filter(Competitor.name.ilike(f"%{competitor_id}%"))

    if retailer_name:
        query = query.filter(Retailer.name.ilike(f"%{retailer_name}%"))

    if region:
        query = query.filter(Promotion.geography_region == region.upper())

    promotions = query.order_by(Promotion.rank_score.desc(), Promotion.last_seen_at.desc()).all()

    rows: List[Dict[str, Any]] = []
    target_campaign = campaign_code.upper() if campaign_code else None

    for p in promotions:
        # Campaign tagging
        tags = detect_campaign_tags(p)
        codes = [t["code"] for t in tags]
        labels = [t["label"] for t in tags]

        # Campaign filter
        if target_campaign and target_campaign not in codes:
            continue

        # Economics
        grams = parse_pack_grams(p.pack_size)
        eff_price = effective_pack_price(p)
        unit_price = per_100g(eff_price, grams)

        # Undercut check: does this competitor item undercut any active product in our portfolio?
        undercuts = False
        cat_own_units = own_by_cat.get((p.category or "").upper(), [])
        if unit_price is not None and cat_own_units:
            undercuts = any(unit_price < our_unit for our_unit in cat_own_units)

        # Evidence
        ev_quote = ""
        ev_url = ""
        if p.evidence_items:
            ev = p.evidence_items[0]
            ev_quote = getattr(ev, "evidence_text", "") or ""
            ev_url = getattr(ev, "source_url", "") or ""

        row: Dict[str, Any] = {
            "promotion_id": str(p.id),
            "product_name": p.product_name,
            "brand": p.brand.name if p.brand else "Unbranded",
            "competitor": p.competitor.name if p.competitor else "Unknown",
            "category": p.category or "OTHER",
            "pack_size": p.pack_size or "Unknown",
            "pack_grams": grams,
            "regular_price": p.regular_price,
            "promo_price": p.promo_price,
            "effective_pack_price": eff_price,
            "price_per_100g": unit_price,
            "discount_percentage": round(p.discount_percentage, 1) if p.discount_percentage is not None else None,
            "promotion_type": p.promotion_type,
            "campaign_codes": ",".join(codes),
            "campaign_labels": ", ".join(labels),
            "retailer": p.retailer.name if p.retailer else "Modern Trade",
            "channel": p.channel or "Offline",
            "geography_region": p.geography_region or "UNKNOWN",
            "geography_raw": p.geography or "",
            "start_date": p.start_date.strftime("%Y-%m-%d") if p.start_date else None,
            "end_date": p.end_date.strftime("%Y-%m-%d") if p.end_date else None,
            "dates_stated": p.start_date is not None or p.end_date is not None,
            "status": p.status,
            "is_active": p.status == "ACTIVE" and (p.end_date is None or p.end_date >= now),
            "rank_score": round(p.rank_score, 1) if p.rank_score is not None else 0.0,
            "ai_confidence": round(p.ai_confidence, 2) if p.ai_confidence is not None else 0.0,
            "source_reliability": round(p.source_reliability, 2) if p.source_reliability is not None else 0.0,
            "has_conflict": p.has_open_conflict,
            "undercuts_our_product": undercuts,
            "first_seen_at": p.first_seen_at.isoformat() if p.first_seen_at else None,
            "last_seen_at": p.last_seen_at.isoformat() if p.last_seen_at else None,
            "last_verified_at": p.last_verified_at.isoformat() if p.last_verified_at else None,
            "source_url": ev_url,
            "evidence_quote": ev_quote,
        }
        rows.append(row)

    return rows


def export_bi_feed_csv(rows: List[Dict[str, Any]]) -> str:
    """Export BI rows as an RFC-4180 CSV with Excel BOM and formula injection protection."""
    buf = io.StringIO()
    # Write UTF-8 BOM so Excel on Windows / Mac displays Indonesian characters and formatting correctly
    buf.write("\ufeff")
    writer = csv.writer(buf)
    writer.writerow(BI_FEED_COLUMNS)
    for r in rows:
        writer.writerow([safe_cell(r.get(col)) for col in BI_FEED_COLUMNS])
    return buf.getvalue()
