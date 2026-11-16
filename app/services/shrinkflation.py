"""Shrinkflation and Unit Price Trend Intelligence Engine.

Identifies FMCG competitor pack downsizing where product weight (grams) decreases
while regular prices remain flat or increase, resulting in stealth unit price inflation.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.entity import Brand, Competitor, Retailer
from app.models.promotion import Promotion
from app.services.comparison import parse_pack_grams, per_100g

logger = logging.getLogger(__name__)


def _normalize_name_for_grouping(name: str) -> str:
    """Strip pack sizes, numbers, and punctuation to match product lines across pack changes."""
    text = name.lower()
    # Remove pack sizes e.g. 300g, 150 gr, 1.5kg, 12x25g
    text = re.sub(r"\b\d+(?:[.,]\d+)?\s*(?:x\s*\d+(?:[.,]\d+)?)?\s*(?:kg|kilogram|gram|gr|g|ml|l)\b", "", text)
    # Remove promo keywords
    text = re.sub(r"\b(promo|diskon|hemat|beli\s*\d+|gratis\s*\d+|special|pack|kemasan\s*baru)\b", "", text)
    # Remove non-alphanumeric
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def detect_shrinkflation(
    db: Session,
    *,
    days: int = 180,
    min_downsize_pct: float = 5.0,
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Scan historical promotions to uncover pack downsizing and hidden price-per-gram inflation."""
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=days)

    promotions = (
        db.query(Promotion)
        .outerjoin(Competitor, Promotion.competitor_id == Competitor.id)
        .outerjoin(Brand, Promotion.brand_id == Brand.id)
        .outerjoin(Retailer, Promotion.retailer_id == Retailer.id)
        .filter(Promotion.first_seen_at >= since)
        .order_by(Promotion.first_seen_at.asc())
        .all()
    )

    # Group by competitor + base product name
    grouped: Dict[Tuple[Optional[str], Optional[str], str], List[Promotion]] = {}
    for p in promotions:
        grams = parse_pack_grams(p.pack_size)
        if not grams or grams <= 0:
            continue
        comp_name = p.competitor.name if p.competitor else None
        brand_name = p.brand.name if p.brand else None
        base_name = _normalize_name_for_grouping(p.product_name)
        if len(base_name) < 3:
            continue
        key = (comp_name, brand_name, base_name)
        grouped.setdefault(key, []).append(p)

    shrinkflation_events: List[Dict[str, Any]] = []

    for (comp_name, brand_name, base_name), items in grouped.items():
        if len(items) < 2:
            continue

        # Sort chronologically by first_seen_at
        items.sort(key=lambda x: x.first_seen_at or now)

        # Compare earliest known baseline vs newest observation
        baseline = items[0]
        latest = items[-1]

        base_grams = parse_pack_grams(baseline.pack_size)
        latest_grams = parse_pack_grams(latest.pack_size)

        if not base_grams or not latest_grams or base_grams <= latest_grams:
            continue

        downsize_grams = round(base_grams - latest_grams, 1)
        downsize_pct = round((downsize_grams / base_grams) * 100.0, 1)

        if downsize_pct < min_downsize_pct:
            continue

        # Check prices
        base_price = baseline.regular_price or baseline.promo_price
        latest_price = latest.regular_price or latest.promo_price

        if not base_price or not latest_price or base_price <= 0 or latest_price <= 0:
            continue

        base_unit = per_100g(base_price, base_grams)
        latest_unit = per_100g(latest_price, latest_grams)

        if not base_unit or not latest_unit:
            continue

        unit_inflation_pct = round(((latest_unit - base_unit) / base_unit) * 100.0, 1)

        # Downsize is considered shrinkflation if price-per-gram increased or stayed virtually flat (>= -2%)
        if unit_inflation_pct >= -2.0:
            shrinkflation_events.append({
                "competitor": comp_name or "Competitor",
                "brand": brand_name or "Brand",
                "product_family": base_name.title(),
                "baseline_product": baseline.product_name,
                "latest_product": latest.product_name,
                "baseline_date": baseline.first_seen_at.strftime("%Y-%m-%d") if baseline.first_seen_at else None,
                "latest_date": latest.first_seen_at.strftime("%Y-%m-%d") if latest.first_seen_at else None,
                "old_pack_size": baseline.pack_size,
                "new_pack_size": latest.pack_size,
                "old_grams": base_grams,
                "new_grams": latest_grams,
                "downsize_grams": downsize_grams,
                "downsize_pct": downsize_pct,
                "old_price": base_price,
                "new_price": latest_price,
                "old_unit_price_per_100g": base_unit,
                "new_unit_price_per_100g": latest_unit,
                "unit_price_inflation_pct": unit_inflation_pct,
                "category": latest.category or baseline.category or "OTHER",
                "outlet": latest.retailer.name if latest.retailer else "Modern Trade",
            })

    shrinkflation_events.sort(key=lambda x: -x["unit_price_inflation_pct"])
    return shrinkflation_events
