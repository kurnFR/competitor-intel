"""Compare our products' shelf prices with competitor promotions (price per 100 g)."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session, contains_eager

from app.models.entity import Brand, Competitor, Retailer
from app.models.own_product import OwnProduct
from app.models.promotion import Promotion
from app.services.promotions.visibility import live_promotion_filter

_UNIT = r"(kg|kilogram|gram|gr|g)\b"
_NUM = r"(\d+(?:[.,]\d+)?)"
_MULTI = re.compile(rf"{_NUM}\s*[x\u00d7]\s*{_NUM}\s*{_UNIT}", re.I)      # 12 x 25 g
_SINGLE = re.compile(rf"{_NUM}\s*{_UNIT}", re.I)                          # 300 g, 1,5 kg

# Compare only packs of broadly similar size (per-100 g normalises the rest).
MIN_PACK_RATIO, MAX_PACK_RATIO = 0.5, 2.0
MAX_MATCHES = 5


def _to_float(text: str) -> float:
    return float(text.replace(",", "."))


def _grams(amount: float, unit: str) -> float:
    return amount * 1000 if unit.lower().startswith("k") else amount


def parse_pack_grams(pack_size: Optional[str]) -> Optional[float]:
    """'300g' -> 300, '1,5 kg' -> 1500, '12x25g' -> 300. None when unknown."""
    if not pack_size:
        return None
    text = str(pack_size)
    m = _MULTI.search(text)
    if m:
        return round(_to_float(m.group(1)) * _grams(_to_float(m.group(2)), m.group(3)), 2)
    m = _SINGLE.search(text)
    if m:
        grams = _grams(_to_float(m.group(1)), m.group(2))
        return grams if grams > 0 else None
    return None


def effective_pack_price(p: Any) -> Optional[float]:
    """Price a shopper effectively pays for one pack under this promotion, if it can be computed."""
    base = p.promo_price
    if base is None and p.regular_price is not None and p.discount_percentage is not None:
        base = p.regular_price * (1 - p.discount_percentage / 100.0)
    if base is None or base <= 0:
        return None
    if p.promotion_type == "BUY_X_GET_Y" and p.buy_quantity and p.free_quantity and p.buy_quantity > 0:
        base = base * p.buy_quantity / (p.buy_quantity + p.free_quantity)
    return round(base, 2)


def per_100g(price: Optional[float], grams: Optional[float]) -> Optional[float]:
    if price is None or not grams or grams <= 0:
        return None
    return round(price / grams * 100.0, 2)


def build_comparison(db: Session, *, days: int = 90, category: Optional[str] = None,
                     now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    own_q = db.query(OwnProduct).filter(OwnProduct.is_active.is_(True))
    if category:
        own_q = own_q.filter(OwnProduct.category == category.upper())
    own_products = own_q.order_by(OwnProduct.category, OwnProduct.name).all()

    promos = (
        db.query(Promotion)
        .outerjoin(Competitor, Promotion.competitor_id == Competitor.id)
        .outerjoin(Brand, Promotion.brand_id == Brand.id)
        .outerjoin(Retailer, Promotion.retailer_id == Retailer.id)
        .options(contains_eager(Promotion.competitor), contains_eager(Promotion.brand), contains_eager(Promotion.retailer))
        .filter(live_promotion_filter(now, recency_days=days))
        .all()
    )
    candidates = []
    for p in promos:
        grams = parse_pack_grams(p.pack_size)
        price = effective_pack_price(p)
        unit = per_100g(price, grams)
        if unit is not None:
            candidates.append((p, grams, price, unit))

    rows: List[Dict[str, Any]] = []
    for own in own_products:
        own_grams = own.pack_grams or parse_pack_grams(own.pack_size)
        own_unit = per_100g(own.regular_price, own_grams)
        item: Dict[str, Any] = {
            "id": str(own.id), "name": own.name, "brand": own.brand, "category": own.category,
            "pack_size": own.pack_size, "regular_price": own.regular_price, "price_per_100g": own_unit,
            "comparable": [], "undercut_count": 0, "largest_gap_pct": None,
            "note": None,
        }
        if own_unit is None:
            item["note"] = "Add a pack size in grams (for example 300g) to enable comparison."
            rows.append(item)
            continue
        matches = []
        for p, grams, price, unit in candidates:
            if (p.category or "").upper() != own.category.upper():
                continue
            ratio = grams / own_grams
            if not (MIN_PACK_RATIO <= ratio <= MAX_PACK_RATIO):
                continue
            gap = round((unit - own_unit) / own_unit * 100.0, 1)   # negative = competitor is cheaper
            matches.append({
                "promotion_id": str(p.id), "product": p.product_name,
                "competitor": p.competitor.name if p.competitor else None,
                "brand": p.brand.name if p.brand else None,
                "outlet": p.retailer.name if p.retailer else None,
                "pack_size": p.pack_size, "promotion_type": p.promotion_type,
                "effective_pack_price": price, "price_per_100g": unit, "gap_pct": gap,
                "undercuts_us": gap < 0,
                "valid_until": p.end_date.strftime("%Y-%m-%d") if p.end_date else None,
                "dates_stated": p.start_date is not None or p.end_date is not None,
            })
        matches.sort(key=lambda m: m["price_per_100g"])
        item["undercut_count"] = sum(1 for m in matches if m["undercuts_us"])
        item["largest_gap_pct"] = min((m["gap_pct"] for m in matches), default=None)
        item["comparable_total"] = len(matches)
        item["comparable"] = matches[:MAX_MATCHES]
        rows.append(item)

    rows.sort(key=lambda r: (r["largest_gap_pct"] is None, r["largest_gap_pct"] if r["largest_gap_pct"] is not None else 0))
    return {
        "generated_at": now.isoformat(),
        "summary": {
            "own_products": len(rows),
            "under_pressure": sum(1 for r in rows if r["undercut_count"] > 0),
            "not_comparable": sum(1 for r in rows if r["price_per_100g"] is None),
        },
        "products": rows,
    }


_THOUSANDS_DOT = re.compile(r"\d{1,3}(\.\d{3})+(,\d+)?")


def parse_price(value: Any) -> float:
    """Parse '12500', '12.500', 'Rp 12.500,50', '12,5' into a float. Raises ValueError."""
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        text = re.sub(r"(?i)rp\.?|idr|\s", "", str(value or ""))
        if not text:
            raise ValueError("price is empty")
        if _THOUSANDS_DOT.fullmatch(text):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", ".")
        number = float(text)
    if not (0 < number < 10_000_000):
        raise ValueError("price must be greater than 0 and below 10,000,000")
    return number
