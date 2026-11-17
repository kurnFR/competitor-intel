"""Compare our products' shelf prices with competitor promotions (price per 100 g)."""
from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple, Union
from uuid import UUID

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session, contains_eager

from app.models.entity import Brand, Competitor, Retailer
from app.models.own_product import OwnProduct
from app.models.promotion import Promotion
from app.services.exporting import safe_cell
from app.services.promotions.visibility import live_promotion_filter

_UNIT = r"(kg|kilogram|gram|gr|g)\b"
_NUM = r"(\d+(?:[.,]\d+)?)"
_MULTI = re.compile(rf"{_NUM}\s*[x\u00d7]\s*{_NUM}\s*{_UNIT}", re.I)      # 12 x 25 g
_SINGLE = re.compile(rf"{_NUM}\s*{_UNIT}", re.I)                          # 300 g, 1,5 kg

CATEGORIES = ("BISCUIT", "CRACKER", "COOKIE", "WAFER", "SNACK")
MIN_PACK_RATIO, MAX_PACK_RATIO = 0.5, 2.0
MAX_MATCHES = 5
DEFAULT_UNSTATED_RECENCY_DAYS = 14
DEFAULT_MAX_RECENCY_DAYS = 90


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


def effective_pack_price(p: Any, price_type: str = "promo") -> Optional[float]:
    """Price a shopper effectively pays for one pack under this promotion or product.

    Supports dual-state pricing:
    - price_type="promo" (default): promotional price after mechanic adjustments (e.g. BUY_X_GET_Y).
    - price_type="regular": regular shelf pack price before discounts.
    """
    if p is None:
        return None

    def _get(key: str, default=None):
        if isinstance(p, dict):
            return p.get(key, default)
        return getattr(p, key, default)

    if price_type == "regular":
        base = _get("regular_price")
        if base is None:
            promo_p = _get("promo_price")
            disc = _get("discount_percentage")
            if promo_p is not None and disc is not None and 0 < disc < 100:
                base = promo_p / (1.0 - disc / 100.0)
        if base is None or base <= 0:
            return None
        return round(float(base), 2)

    # price_type == "promo"
    base = _get("promo_price")
    reg_price = _get("regular_price")
    disc = _get("discount_percentage")

    if base is None and reg_price is not None and disc is not None and disc > 0:
        base = reg_price * (1.0 - disc / 100.0)

    ptype = _get("promotion_type") or _get("promo_type") or "DISCOUNT"
    buy_q = _get("buy_quantity") or _get("buy_x")
    free_q = _get("free_quantity") or _get("get_y")

    # If base is still None but it's BUY_X_GET_Y with regular price
    if base is None and reg_price is not None and ptype == "BUY_X_GET_Y":
        base = reg_price

    if base is None or base <= 0:
        return None

    if ptype == "BUY_X_GET_Y" and buy_q and free_q and buy_q > 0:
        base = base * buy_q / (buy_q + free_q)

    return round(float(base), 2)


def per_100g(price: Any, grams: Optional[float] = None, *, price_type: str = "promo") -> Optional[float]:
    """Calculate unit price per 100 grams.

    Can be invoked with numeric price and pack grams:
        per_100g(7000, 300) -> 2333.33
    Or directly with an object (OwnProduct, Promotion, etc.):
        per_100g(obj, price_type="regular")
    """
    if grams is None and price is not None and not isinstance(price, (int, float)):
        obj = price
        if isinstance(obj, dict):
            grams = obj.get("pack_grams") or parse_pack_grams(obj.get("pack_size"))
        else:
            grams = getattr(obj, "pack_grams", None) or parse_pack_grams(getattr(obj, "pack_size", None))
        price = effective_pack_price(obj, price_type=price_type)

    if price is None or not grams:
        return None

    try:
        p = float(price)
        g = float(grams)
        if p <= 0 or g <= 0:
            return None
        return round(p / g * 100.0, 2)
    except (TypeError, ValueError):
        return None


def calculate_gap_pct(competitor_per_100g: Optional[float], own_per_100g: Optional[float]) -> Optional[float]:
    """Gap percentage between competitor unit price and our unit price per 100 g.

    Formula: ((competitor - own) / own) * 100.0
    Negative value means competitor is cheaper than us (e.g. -25.0 means 25% cheaper).
    Positive value means competitor is more expensive than us (e.g. +20.0 means 20% dearer).
    """
    if competitor_per_100g is None or own_per_100g is None or own_per_100g <= 0:
        return None
    return round((competitor_per_100g - own_per_100g) / own_per_100g * 100.0, 1)


def is_valid_active_promotion(
    p: Promotion,
    now: datetime,
    *,
    unstated_recency_days: int = DEFAULT_UNSTATED_RECENCY_DAYS,
    max_recency_days: int = DEFAULT_MAX_RECENCY_DAYS,
) -> bool:
    """Strict multi-source validity check.

    Ensures only active competitor promotions are reported:
    - Status is 'ACTIVE' (or 'UNKNOWN' for promotions with unstated dates).
    - If start_date is set, now >= start_date (no future promotions).
    - If end_date is set, now <= end_date (no expired promotions).
    - For promotions with unstated dates (neither start nor end date),
      last_verified_at must be within unstated_recency_days (default 14 days).
    - For promotions with stated dates, last_verified_at must be within max_recency_days.
    - Not in open conflict.
    """
    if p.status not in ("ACTIVE", "UNKNOWN"):
        return False
    if getattr(p, "has_open_conflict", False):
        return False

    # Check date window with timezone-safe comparisons
    now_utc = now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
    if p.start_date is not None:
        start_utc = p.start_date if p.start_date.tzinfo is not None else p.start_date.replace(tzinfo=timezone.utc)
        if now_utc < start_utc:
            return False
    if p.end_date is not None:
        end_utc = p.end_date if p.end_date.tzinfo is not None else p.end_date.replace(tzinfo=timezone.utc)
        if now_utc > end_utc:
            return False

    verified_at = p.last_verified_at or p.last_seen_at
    if verified_at is None:
        return False
    verified_utc = verified_at if verified_at.tzinfo is not None else verified_at.replace(tzinfo=timezone.utc)

    has_dates = p.start_date is not None or p.end_date is not None
    if not has_dates:
        if verified_utc < now_utc - timedelta(days=unstated_recency_days):
            return False
    else:
        if verified_utc < now_utc - timedelta(days=max_recency_days):
            return False

    return True


def is_product_match(
    own: Any,
    promo: Any,
    *,
    own_grams: Optional[float],
    promo_grams: Optional[float],
    min_pack_ratio: float = MIN_PACK_RATIO,
    max_pack_ratio: float = MAX_PACK_RATIO,
    sku_mappings: Optional[Dict[str, List[str]]] = None,
    brand_mappings: Optional[Dict[str, List[str]]] = None,
) -> bool:
    """Matches competitor promotions against own products by:
    1. Category (BISCUIT, CRACKER, COOKIE, WAFER, SNACK).
    2. Normalized pack grams ratio (0.5x to 2.0x).
    3. Optional direct brand/SKU mappings.
    """
    own_cat = (getattr(own, "category", "") or (own.get("category") if isinstance(own, dict) else "") or "").strip().upper()
    promo_cat = (getattr(promo, "category", "") or (promo.get("category") if isinstance(promo, dict) else "") or "").strip().upper()

    if not own_cat or not promo_cat or own_cat != promo_cat:
        return False

    own_sku = (getattr(own, "sku", None) or (own.get("sku") if isinstance(own, dict) else None) or "").strip()
    promo_sku = (getattr(promo, "sku", None) or (promo.get("sku") if isinstance(promo, dict) else None) or "").strip()

    # Optional direct SKU mappings
    if sku_mappings and own_sku:
        target_skus = [s.strip() for s in sku_mappings.get(own_sku, [])]
        if target_skus:
            if not promo_sku or promo_sku not in target_skus:
                return False

    # Optional direct brand mappings
    own_brand = (getattr(own, "brand", None) or (own.get("brand") if isinstance(own, dict) else None) or "").strip()
    promo_brand_name = None
    if isinstance(promo, dict):
        promo_brand_name = promo.get("brand") or promo.get("competitor")
    else:
        if promo.brand and hasattr(promo.brand, "name"):
            promo_brand_name = promo.brand.name
        elif promo.competitor and hasattr(promo.competitor, "name"):
            promo_brand_name = promo.competitor.name

    if brand_mappings and own_brand:
        target_brands = [b.strip().upper() for b in brand_mappings.get(own_brand, [])]
        if target_brands:
            if not promo_brand_name or promo_brand_name.strip().upper() not in target_brands:
                return False

    # Normalized pack grams ratio
    if not own_grams or not promo_grams or own_grams <= 0 or promo_grams <= 0:
        return False

    ratio = promo_grams / own_grams
    if not (min_pack_ratio <= ratio <= max_pack_ratio):
        return False

    return True


def build_aggregations(
    candidates: List[Tuple[Promotion, float, float, float, Optional[float], Optional[float]]],
    own_products: List[OwnProduct],
) -> Dict[str, Any]:
    """Break down competitor promo activities by brand, category, retailer/channel, and mechanic."""
    by_brand_map: Dict[str, Dict[str, Any]] = {}
    by_cat_map: Dict[str, Dict[str, Any]] = {}
    by_ret_map: Dict[str, Dict[str, Any]] = {}
    by_mech_map: Dict[str, Dict[str, Any]] = {}

    own_by_cat: Dict[str, List[Tuple[OwnProduct, float, Optional[float]]]] = {}
    for own in own_products:
        cat = (own.category or "").upper()
        g = own.pack_grams or parse_pack_grams(own.pack_size)
        reg_unit = per_100g(own.regular_price, g)
        promo_unit = per_100g(own.promo_price, g) if own.has_active_promo else None
        if reg_unit is not None:
            own_by_cat.setdefault(cat, []).append((own, reg_unit, promo_unit))

    for p, grams, promo_price, promo_unit, reg_price, reg_unit in candidates:
        cat = (p.category or "OTHER").upper()
        brand_name = p.brand.name if p.brand else (p.competitor.name if p.competitor else "Unknown")
        comp_name = p.competitor.name if p.competitor else None
        ret_name = p.retailer.name if p.retailer else "Unknown"
        channel_type = p.retailer.channel_type if p.retailer else None
        mech = p.promotion_type or "DISCOUNT"
        disc = p.discount_percentage

        undercuts_any = False
        cat_owns = own_by_cat.get(cat, [])
        for own_prod, own_reg_u, own_promo_u in cat_owns:
            own_g = own_prod.pack_grams or 1
            ratio = grams / own_g
            if MIN_PACK_RATIO <= ratio <= MAX_PACK_RATIO:
                target_unit = own_promo_u if own_promo_u is not None else own_reg_u
                if promo_unit < target_unit:
                    undercuts_any = True
                    break

        # 1. By Brand
        if brand_name not in by_brand_map:
            by_brand_map[brand_name] = {
                "brand": brand_name,
                "competitor": comp_name,
                "count": 0,
                "undercut_count": 0,
                "prices_per_100g": [],
                "discounts": [],
                "mechanics": set(),
            }
        b_entry = by_brand_map[brand_name]
        b_entry["count"] += 1
        if undercuts_any:
            b_entry["undercut_count"] += 1
        b_entry["prices_per_100g"].append(promo_unit)
        if disc is not None:
            b_entry["discounts"].append(disc)
        b_entry["mechanics"].add(mech)

        # 2. By Category
        if cat not in by_cat_map:
            by_cat_map[cat] = {
                "category": cat,
                "count": 0,
                "undercut_count": 0,
                "prices_per_100g": [],
                "brands": set(),
                "retailers": set(),
            }
        c_entry = by_cat_map[cat]
        c_entry["count"] += 1
        if undercuts_any:
            c_entry["undercut_count"] += 1
        c_entry["prices_per_100g"].append(promo_unit)
        c_entry["brands"].add(brand_name)
        c_entry["retailers"].add(ret_name)

        # 3. By Retailer / Channel
        if ret_name not in by_ret_map:
            by_ret_map[ret_name] = {
                "retailer": ret_name,
                "channel_type": channel_type,
                "count": 0,
                "undercut_count": 0,
                "prices_per_100g": [],
                "discounts": [],
                "mechanic_counts": {},
            }
        r_entry = by_ret_map[ret_name]
        r_entry["count"] += 1
        if undercuts_any:
            r_entry["undercut_count"] += 1
        r_entry["prices_per_100g"].append(promo_unit)
        if disc is not None:
            r_entry["discounts"].append(disc)
        r_entry["mechanic_counts"][mech] = r_entry["mechanic_counts"].get(mech, 0) + 1

        # 4. By Mechanic
        if mech not in by_mech_map:
            by_mech_map[mech] = {
                "mechanic": mech,
                "count": 0,
                "undercut_count": 0,
                "prices_per_100g": [],
                "discounts": [],
            }
        m_entry = by_mech_map[mech]
        m_entry["count"] += 1
        if undercuts_any:
            m_entry["undercut_count"] += 1
        m_entry["prices_per_100g"].append(promo_unit)
        if disc is not None:
            m_entry["discounts"].append(disc)

    # 5. By Competitor
    by_comp_map: Dict[str, Dict[str, Any]] = {}
    for p, grams, promo_price, promo_unit, reg_price, reg_unit in candidates:
        comp_name = p.competitor.name if p.competitor else (p.brand.name if p.brand else "Unknown")
        if comp_name not in by_comp_map:
            by_comp_map[comp_name] = {"competitor": comp_name, "count": 0, "brands": set()}
        by_comp_map[comp_name]["count"] += 1
        brand_name = p.brand.name if p.brand else None
        if brand_name:
            by_comp_map[comp_name]["brands"].add(brand_name)

    competitor_list = [
        {"competitor": v["competitor"], "count": v["count"], "brand_count": len(v["brands"])}
        for v in by_comp_map.values()
    ]
    competitor_list.sort(key=lambda x: -x["count"])

    brand_list = [
        {
            "brand": v["brand"],
            "competitor": v["competitor"],
            "count": v["count"],
            "undercut_count": v["undercut_count"],
            "avg_price_per_100g": round(sum(v["prices_per_100g"]) / len(v["prices_per_100g"]), 2),
            "min_price_per_100g": min(v["prices_per_100g"]),
            "max_price_per_100g": max(v["prices_per_100g"]),
            "avg_discount_pct": round(sum(v["discounts"]) / len(v["discounts"]), 1) if v["discounts"] else None,
            "mechanics": sorted(list(v["mechanics"])),
        }
        for v in by_brand_map.values()
    ]
    brand_list.sort(key=lambda x: -x["count"])

    category_list = [
        {
            "category": v["category"],
            "count": v["count"],
            "undercut_count": v["undercut_count"],
            "avg_price_per_100g": round(sum(v["prices_per_100g"]) / len(v["prices_per_100g"]), 2),
            "min_price_per_100g": min(v["prices_per_100g"]),
            "max_price_per_100g": max(v["prices_per_100g"]),
            "brand_count": len(v["brands"]),
            "retailer_count": len(v["retailers"]),
        }
        for v in by_cat_map.values()
    ]
    category_list.sort(key=lambda x: -x["count"])

    retailer_list = [
        {
            "retailer": v["retailer"],
            "channel_type": v["channel_type"],
            "count": v["count"],
            "undercut_count": v["undercut_count"],
            "avg_price_per_100g": round(sum(v["prices_per_100g"]) / len(v["prices_per_100g"]), 2),
            "min_price_per_100g": min(v["prices_per_100g"]),
            "avg_discount_pct": round(sum(v["discounts"]) / len(v["discounts"]), 1) if v["discounts"] else None,
            "top_mechanic": max(v["mechanic_counts"].items(), key=lambda i: i[1])[0] if v["mechanic_counts"] else None,
        }
        for v in by_ret_map.values()
    ]
    retailer_list.sort(key=lambda x: -x["count"])

    mechanic_list = [
        {
            "mechanic": v["mechanic"],
            "count": v["count"],
            "undercut_count": v["undercut_count"],
            "avg_price_per_100g": round(sum(v["prices_per_100g"]) / len(v["prices_per_100g"]), 2),
            "avg_discount_pct": round(sum(v["discounts"]) / len(v["discounts"]), 1) if v["discounts"] else None,
        }
        for v in by_mech_map.values()
    ]
    mechanic_list.sort(key=lambda x: -x["count"])

    return {
        "total_active_promotions": len(candidates),
        "by_brand": brand_list,
        "by_competitor": competitor_list,
        "by_category": category_list,
        "by_retailer": retailer_list,
        "by_mechanic": mechanic_list,
    }


def build_comparison(
    db: Session,
    *,
    days: int = DEFAULT_MAX_RECENCY_DAYS,
    unstated_recency_days: int = DEFAULT_UNSTATED_RECENCY_DAYS,
    category: Optional[str] = None,
    brand: Optional[str] = None,
    competitor: Optional[str] = None,
    retailer: Optional[str] = None,
    channel: Optional[str] = None,
    sku_mappings: Optional[Dict[str, List[str]]] = None,
    brand_mappings: Optional[Dict[str, List[str]]] = None,
    min_pack_ratio: float = MIN_PACK_RATIO,
    max_pack_ratio: float = MAX_PACK_RATIO,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    own_q = db.query(OwnProduct).filter(OwnProduct.is_active.is_(True))
    if category:
        own_q = own_q.filter(OwnProduct.category == category.upper())
    if brand:
        brand_matched_owns = own_q.filter(OwnProduct.brand == brand).all()
        if brand_matched_owns:
            own_products = brand_matched_owns
        else:
            own_products = own_q.order_by(OwnProduct.category, OwnProduct.name).all()
    else:
        own_products = own_q.order_by(OwnProduct.category, OwnProduct.name).all()

    # Query active competitor promotions using live filter + strict validity window
    promos_q = (
        db.query(Promotion)
        .outerjoin(Competitor, Promotion.competitor_id == Competitor.id)
        .outerjoin(Brand, Promotion.brand_id == Brand.id)
        .outerjoin(Retailer, Promotion.retailer_id == Retailer.id)
        .options(
            contains_eager(Promotion.competitor),
            contains_eager(Promotion.brand),
            contains_eager(Promotion.retailer),
        )
        .filter(live_promotion_filter(now, recency_days=days))
    )

    # Date validity filters in SQL
    promos_q = promos_q.filter(
        or_(Promotion.start_date.is_(None), Promotion.start_date <= now),
        or_(Promotion.end_date.is_(None), Promotion.end_date >= now),
        or_(
            Promotion.start_date.isnot(None),
            Promotion.end_date.isnot(None),
            Promotion.last_verified_at >= now - timedelta(days=unstated_recency_days),
        ),
    )

    if category:
        promos_q = promos_q.filter(Promotion.category == category.upper())
    if competitor:
        promos_q = promos_q.filter(Competitor.name.ilike(f"%{competitor}%"))
    if brand:
        promos_q = promos_q.filter(or_(Brand.name.ilike(f"%{brand}%"), Competitor.name.ilike(f"%{brand}%")))
    if retailer:
        promos_q = promos_q.filter(Retailer.name.ilike(f"%{retailer}%"))
    if channel:
        promos_q = promos_q.filter(Retailer.channel_type == channel.upper())

    promos = promos_q.all()

    # Python-level verification & candidate calculation
    candidates: List[Tuple[Promotion, float, float, float, Optional[float], Optional[float]]] = []
    for p in promos:
        if not is_valid_active_promotion(p, now, unstated_recency_days=unstated_recency_days, max_recency_days=days):
            continue
        grams = parse_pack_grams(p.pack_size)
        promo_price = effective_pack_price(p, price_type="promo")
        promo_unit = per_100g(promo_price, grams)
        if promo_unit is not None and grams is not None:
            reg_price = effective_pack_price(p, price_type="regular")
            reg_unit = per_100g(reg_price, grams)
            candidates.append((p, grams, promo_price, promo_unit, reg_price, reg_unit))

    # Aggregations
    aggregations = build_aggregations(candidates, own_products)

    # Compare each own product
    rows: List[Dict[str, Any]] = []
    now_utc = now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
    for own in own_products:
        own_grams = own.pack_grams or parse_pack_grams(own.pack_size)
        own_regular_unit = per_100g(own.regular_price, own_grams)

        own_has_promo = (
            own.promo_price is not None
            and (own.promo_start_date is None or now >= own.promo_start_date)
            and (own.promo_end_date is None or now <= own.promo_end_date)
        )
        own_promo_pack = effective_pack_price(own, price_type="promo") if own_has_promo else None
        own_promo_unit = per_100g(own_promo_pack, own_grams) if own_has_promo else None

        item: Dict[str, Any] = {
            "id": str(own.id),
            "name": own.name,
            "brand": own.brand,
            "sku": own.sku,
            "category": own.category,
            "pack_size": own.pack_size,
            "pack_grams": own_grams,
            "regular_price": own.regular_price,
            "price_per_100g": own_regular_unit,
            "regular_price_per_100g": own_regular_unit,
            "promo_price": own_promo_pack,
            "promo_price_per_100g": own_promo_unit,
            "has_active_promo": own_has_promo,
            "promo_type": own.promo_type if own_has_promo else None,
            "promo_start_date": own.promo_start_date.strftime("%Y-%m-%d") if own.promo_start_date else None,
            "promo_end_date": own.promo_end_date.strftime("%Y-%m-%d") if own.promo_end_date else None,
            "promo_mechanic": own.promo_mechanic if own_has_promo else None,
            "comparable": [],
            "undercut_count": 0,
            "promo_undercut_count": 0 if own_has_promo else None,
            "largest_gap_pct": None,
            "largest_promo_gap_pct": None,
            "note": None,
        }

        if own_regular_unit is None:
            item["note"] = "Add a pack size in grams (for example 300g) to enable comparison."
            rows.append(item)
            continue

        matches: List[Dict[str, Any]] = []
        for p, grams, promo_price, promo_unit, reg_price, reg_unit in candidates:
            if not is_product_match(
                own,
                p,
                own_grams=own_grams,
                promo_grams=grams,
                min_pack_ratio=min_pack_ratio,
                max_pack_ratio=max_pack_ratio,
                sku_mappings=sku_mappings,
                brand_mappings=brand_mappings,
            ):
                continue

            regular_to_promo_gap = calculate_gap_pct(promo_unit, own_regular_unit)
            promo_to_promo_gap = calculate_gap_pct(promo_unit, own_promo_unit) if own_promo_unit else None
            reg_to_reg_gap = calculate_gap_pct(reg_unit, own_regular_unit) if reg_unit else None

            undercuts_us = regular_to_promo_gap is not None and regular_to_promo_gap < 0
            undercuts_promo = promo_to_promo_gap is not None and promo_to_promo_gap < 0 if own_promo_unit else None

            # Validity status
            p_end = p.end_date
            if p_end is not None:
                p_end_utc = p_end if p_end.tzinfo is not None else p_end.replace(tzinfo=timezone.utc)
                if p_end_utc <= now_utc + timedelta(days=7):
                    v_status = "EXPIRING_SOON"
                else:
                    v_status = "ACTIVE"
                days_left = max(0, (p_end_utc.date() - now_utc.date()).days)
            elif p.start_date is not None:
                v_status = "ACTIVE"
                days_left = None
            else:
                v_status = "ONGOING"
                days_left = None

            comp_disc = p.discount_percentage
            if comp_disc is None and reg_price and promo_price and reg_price > promo_price:
                comp_disc = round((1.0 - promo_price / reg_price) * 100.0, 1)

            matches.append({
                "promotion_id": str(p.id),
                "product": p.product_name,
                "sku": p.sku,
                "competitor": p.competitor.name if p.competitor else None,
                "brand": p.brand.name if p.brand else None,
                "outlet": p.retailer.name if p.retailer else None,
                "retailer": p.retailer.name if p.retailer else None,
                "channel_type": p.retailer.channel_type if p.retailer else None,
                "pack_size": p.pack_size,
                "pack_grams": grams,
                "promotion_type": p.promotion_type,
                "effective_pack_price": promo_price,
                "regular_pack_price": reg_price,
                "price_per_100g": promo_unit,
                "regular_price_per_100g": reg_unit,
                "gap_pct": regular_to_promo_gap,
                "regular_to_promo_gap_pct": regular_to_promo_gap,
                "promo_to_promo_gap_pct": promo_to_promo_gap,
                "regular_to_regular_gap_pct": reg_to_reg_gap,
                "undercuts_us": undercuts_us,
                "undercuts_our_promo": undercuts_promo,
                "valid_from": p.start_date.strftime("%Y-%m-%d") if p.start_date else None,
                "valid_until": p.end_date.strftime("%Y-%m-%d") if p.end_date else None,
                "validity_status": v_status,
                "days_remaining": days_left,
                "discount_percentage": comp_disc,
                "dates_stated": p.start_date is not None or p.end_date is not None,
                "last_verified_at": p.last_verified_at.isoformat() if p.last_verified_at else None,
            })

        matches.sort(key=lambda m: m["price_per_100g"])
        item["undercut_count"] = sum(1 for m in matches if m["undercuts_us"])
        item["largest_gap_pct"] = min((m["gap_pct"] for m in matches if m["gap_pct"] is not None), default=None)
        if own_has_promo:
            item["promo_undercut_count"] = sum(1 for m in matches if m.get("undercuts_our_promo") is True)
            item["largest_promo_gap_pct"] = min(
                (m["promo_to_promo_gap_pct"] for m in matches if m["promo_to_promo_gap_pct"] is not None),
                default=None,
            )
        item["comparable_total"] = len(matches)
        item["comparable"] = matches[:MAX_MATCHES]
        rows.append(item)

    rows.sort(key=lambda r: (r["largest_gap_pct"] is None, r["largest_gap_pct"] if r["largest_gap_pct"] is not None else 0))

    # Executive Overview Calculations
    price_indices = []
    for r in rows:
        eff_unit = r["promo_price_per_100g"] if r["has_active_promo"] and r["promo_price_per_100g"] else r["price_per_100g"]
        if eff_unit and r.get("comparable"):
            c_units = [m["price_per_100g"] for m in r["comparable"] if m.get("price_per_100g")]
            if c_units:
                avg_c = sum(c_units) / len(c_units)
                if avg_c > 0:
                    price_indices.append((eff_unit / avg_c) * 100.0)

    overall_price_index = round(sum(price_indices) / len(price_indices), 1) if price_indices else 100.0
    price_index_gap_pct = round(overall_price_index - 100.0, 1)

    comparable_prods = [r for r in rows if r["price_per_100g"] is not None]
    under_pressure_count = sum(1 for r in comparable_prods if r["undercut_count"] > 0)
    pct_under_pressure = round((under_pressure_count / len(comparable_prods) * 100.0), 1) if comparable_prods else 0.0

    deepest_by_cat: Dict[str, Any] = {}
    deepest_overall = None
    for p, grams, promo_p, promo_u, reg_p, reg_u in candidates:
        cat = (p.category or "OTHER").upper()
        disc = p.discount_percentage
        if disc is None and reg_p and promo_p and reg_p > promo_p:
            disc = round((1.0 - promo_p / reg_p) * 100.0, 1)
        if disc is not None and disc > 0:
            if cat not in deepest_by_cat or disc > deepest_by_cat[cat]["discount_pct"]:
                deepest_by_cat[cat] = {
                    "category": cat,
                    "discount_pct": disc,
                    "product": p.product_name,
                    "competitor": p.competitor.name if p.competitor else (p.brand.name if p.brand else None),
                    "outlet": p.retailer.name if p.retailer else None,
                }
            if deepest_overall is None or disc > deepest_overall["discount_pct"]:
                deepest_overall = deepest_by_cat[cat]

    for cat in CATEGORIES:
        if cat not in deepest_by_cat:
            cat_rows = [r for r in rows if (r.get("category") or "").upper() == cat]
            min_gap = None
            top_m = None
            for r in cat_rows:
                for m in r.get("comparable", []):
                    if m.get("gap_pct") is not None and (min_gap is None or m["gap_pct"] < min_gap):
                        min_gap = m["gap_pct"]
                        top_m = m
            if min_gap is not None and min_gap < 0:
                deepest_by_cat[cat] = {
                    "category": cat,
                    "discount_pct": abs(min_gap),
                    "undercut_pct": min_gap,
                    "product": top_m["product"],
                    "competitor": top_m["competitor"] or top_m["brand"],
                    "outlet": top_m["outlet"],
                }

    total_active_promos = len(candidates)
    brand_count = len(aggregations.get("by_brand", []))
    promos_per_brand = round(total_active_promos / brand_count, 1) if brand_count > 0 else 0.0
    expiring_soon_count = sum(
        1 for p, _, _, _, _, _ in candidates
        if p.end_date is not None and (p.end_date if p.end_date.tzinfo is not None else p.end_date.replace(tzinfo=timezone.utc)) <= now_utc + timedelta(days=7)
    )
    promo_frequency = {
        "total_active_promotions": total_active_promos,
        "brands_tracked": brand_count,
        "avg_promos_per_brand": promos_per_brand,
        "expiring_soon_count": expiring_soon_count,
        "by_category": {c["category"]: c["count"] for c in aggregations.get("by_category", [])},
    }

    return {
        "generated_at": now.isoformat(),
        "summary": {
            "own_products": len(rows),
            "under_pressure": under_pressure_count,
            "not_comparable": sum(1 for r in rows if r["price_per_100g"] is None),
            "active_competitor_promotions": total_active_promos,
            "price_index_vs_market": overall_price_index,
            "price_index_gap_pct": price_index_gap_pct,
            "pct_under_pressure": pct_under_pressure,
            "deepest_discount_by_category": deepest_by_cat,
            "deepest_overall_discount": deepest_overall,
            "promo_frequency": promo_frequency,
        },
        "aggregations": aggregations,
        "products": rows,
    }


def build_comparison_export(data: Dict[str, Any], fmt: str = "csv") -> Tuple[bytes, str, str]:
    """Build formatted CSV or Excel export of the price comparison matrix."""
    headers = [
        "Category", "Our Product", "Our SKU", "Our Pack Size", "Our Regular Price (IDR)",
        "Our Promo Price (IDR)", "Our Promo Type", "Our Price / 100g (IDR)", "Competitor",
        "Competitor Brand", "Competitor Product", "Competitor Pack Size", "Mechanic",
        "Competitor Promo Price (IDR)", "Competitor Price / 100g (IDR)", "Price Gap %",
        "Competitive Status", "Validity Status", "Valid Until", "Outlet", "Channel"
    ]
    rows = []
    for p in data.get("products", []):
        cat = p.get("category", "")
        p_name = p.get("name", "")
        sku = p.get("sku") or ""
        pack = p.get("pack_size") or ""
        reg_price = p.get("regular_price")
        promo_price = p.get("promo_price") if p.get("has_active_promo") else ""
        promo_type = p.get("promo_type") if p.get("has_active_promo") else "REGULAR"
        unit_price = p.get("price_per_100g")

        matches = p.get("comparable", [])
        if not matches:
            rows.append([
                cat, p_name, sku, pack, reg_price, promo_price, promo_type, unit_price,
                "None", "None", "No active competitor promotions", "", "",
                "", "", "", "No Competitor Moves", "", "", "", ""
            ])
        else:
            for m in matches:
                gap = m.get("gap_pct")
                status = f"Undercut ({gap}%)" if gap is not None and gap < 0 else (f"Competitive (+{gap}%)" if gap is not None and gap > 0 else "Parity")
                rows.append([
                    cat, p_name, sku, pack, reg_price, promo_price, promo_type, unit_price,
                    m.get("competitor") or "", m.get("brand") or "", m.get("product") or "",
                    m.get("pack_size") or "", m.get("promotion_type") or "",
                    m.get("effective_pack_price"), m.get("price_per_100g"),
                    f"{gap}%" if gap is not None else "",
                    status,
                    m.get("validity_status") or ("Active" if m.get("dates_stated") else "Ongoing"),
                    m.get("valid_until") or "Ongoing",
                    m.get("outlet") or "",
                    m.get("channel_type") or ""
                ])

    if fmt == "xlsx":
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment
        wb = Workbook()
        ws = wb.active
        ws.title = "Price Comparison"
        ws.append(["Executive Price Comparison & Competitive Position Report"])
        ws.append([f"Generated: {data.get('generated_at', '')} | Overall Price Index: {data.get('summary', {}).get('price_index_vs_market', 100.0)}%"])
        ws.append([])
        ws.append(headers)

        header_row = 4
        title_font = Font(name="Calibri", size=14, bold=True, color="1E3A8A")
        sub_font = Font(name="Calibri", size=10, italic=True, color="475569")
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
        undercut_fill = PatternFill(start_color="FFE4E6", end_color="FFE4E6", fill_type="solid")

        ws.cell(row=1, column=1).font = title_font
        ws.cell(row=2, column=1).font = sub_font
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=header_row, column=col_idx)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")

        for r_idx, row in enumerate(rows, start=header_row + 1):
            for c_idx, val in enumerate(row, start=1):
                cell = ws.cell(row=r_idx, column=c_idx, value=safe_cell(val))
                if len(row) > 16 and "Undercut" in str(row[16]):
                    cell.fill = undercut_fill

        ws.freeze_panes = f"A{header_row + 1}"
        for col in range(1, len(headers) + 1):
            ws.column_dimensions[ws.cell(row=header_row, column=col).column_letter].width = 18

        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    for r in rows:
        writer.writerow([safe_cell(c) for c in r])
    return ("\ufeff" + buf.getvalue()).encode("utf-8"), "text/csv; charset=utf-8", "csv"


def simulate_price(
    db: Session,
    *,
    product_id: Optional[Union[UUID, str]] = None,
    sku: Optional[str] = None,
    name: Optional[str] = "Simulated Product",
    category: str = "BISCUIT",
    pack_size: Optional[str] = None,
    pack_grams: Optional[float] = None,
    regular_price: Optional[float] = None,
    candidate_price: Optional[float] = None,
    candidate_promo_price: Optional[float] = None,
    candidate_regular_price: Optional[float] = None,
    candidate_promo_type: str = "DISCOUNT",
    candidate_discount_percentage: Optional[float] = None,
    buy_quantity: Optional[int] = None,
    free_quantity: Optional[int] = None,
    buy_x: Optional[int] = None,
    get_y: Optional[int] = None,
    min_pack_ratio: float = MIN_PACK_RATIO,
    max_pack_ratio: float = MAX_PACK_RATIO,
    days: int = DEFAULT_MAX_RECENCY_DAYS,
    unstated_recency_days: int = DEFAULT_UNSTATED_RECENCY_DAYS,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """What-if price simulation comparing a proposed price against live competitor promotions."""
    now = now or datetime.now(timezone.utc)
    product: Optional[OwnProduct] = None

    if product_id:
        if isinstance(product_id, str):
            product_id = UUID(product_id)
        product = db.get(OwnProduct, product_id)
        if product is None:
            raise ValueError(f"Own product {product_id} not found.")
    elif sku:
        product = db.query(OwnProduct).filter(OwnProduct.sku == sku).first()

    if product:
        prod_name = name if name and name != "Simulated Product" else product.name
        prod_category = category if category != "BISCUIT" else product.category
        prod_pack_size = pack_size or product.pack_size
        prod_pack_grams = pack_grams or product.pack_grams or parse_pack_grams(prod_pack_size)
        base_regular_price = candidate_regular_price or regular_price or product.regular_price
        curr_has_promo = product.has_active_promo
    else:
        prod_name = name or "Simulated Product"
        prod_category = (category or "BISCUIT").upper()
        prod_pack_size = pack_size
        prod_pack_grams = pack_grams or parse_pack_grams(pack_size)
        base_regular_price = candidate_regular_price or regular_price
        curr_has_promo = False

    if not prod_pack_grams or prod_pack_grams <= 0:
        raise ValueError("Pack size in grams (e.g. '300g' or pack_grams=300) is required for comparison.")

    buy_q = buy_quantity or buy_x
    free_q = free_quantity or get_y

    sim_promo_price = candidate_promo_price or candidate_price
    if sim_promo_price is None and candidate_discount_percentage is not None and base_regular_price:
        sim_promo_price = base_regular_price * (1.0 - candidate_discount_percentage / 100.0)
    elif sim_promo_price is None:
        sim_promo_price = base_regular_price

    if sim_promo_price is None or sim_promo_price <= 0:
        raise ValueError("A valid candidate price or regular price is required.")

    sim_obj = {
        "regular_price": base_regular_price,
        "promo_price": sim_promo_price,
        "promotion_type": candidate_promo_type,
        "buy_quantity": buy_q,
        "free_quantity": free_q,
        "discount_percentage": candidate_discount_percentage,
    }
    candidate_effective_pack = effective_pack_price(sim_obj, price_type="promo")
    candidate_per_100g = per_100g(candidate_effective_pack, prod_pack_grams)

    current_reg_unit = per_100g(base_regular_price, prod_pack_grams) if base_regular_price else None
    current_promo_pack = effective_pack_price(product, price_type="promo") if (product and curr_has_promo) else None
    current_promo_unit = per_100g(current_promo_pack, prod_pack_grams) if curr_has_promo else None
    baseline_effective_unit = current_promo_unit if curr_has_promo and current_promo_unit else current_reg_unit

    promos_q = (
        db.query(Promotion)
        .outerjoin(Competitor, Promotion.competitor_id == Competitor.id)
        .outerjoin(Brand, Promotion.brand_id == Brand.id)
        .outerjoin(Retailer, Promotion.retailer_id == Retailer.id)
        .options(
            contains_eager(Promotion.competitor),
            contains_eager(Promotion.brand),
            contains_eager(Promotion.retailer),
        )
        .filter(
            live_promotion_filter(now, recency_days=days),
            Promotion.category == prod_category,
            or_(Promotion.start_date.is_(None), Promotion.start_date <= now),
            or_(Promotion.end_date.is_(None), Promotion.end_date >= now),
            or_(
                Promotion.start_date.isnot(None),
                Promotion.end_date.isnot(None),
                Promotion.last_verified_at >= now - timedelta(days=unstated_recency_days),
            ),
        )
    )
    promos = promos_q.all()

    comparable_matches = []
    comp_units = []

    for p in promos:
        if not is_valid_active_promotion(p, now, unstated_recency_days=unstated_recency_days, max_recency_days=days):
            continue
        g = parse_pack_grams(p.pack_size)
        if not g or g <= 0:
            continue
        ratio = g / prod_pack_grams
        if not (min_pack_ratio <= ratio <= max_pack_ratio):
            continue
        c_price = effective_pack_price(p, price_type="promo")
        c_unit = per_100g(c_price, g)
        if c_unit is None:
            continue

        comp_units.append(c_unit)
        gap_vs_candidate = calculate_gap_pct(c_unit, candidate_per_100g)
        gap_vs_baseline = calculate_gap_pct(c_unit, baseline_effective_unit) if baseline_effective_unit else None

        undercuts_cand = c_unit < candidate_per_100g
        undercuts_base = baseline_effective_unit is not None and c_unit < baseline_effective_unit

        comparable_matches.append({
            "promotion_id": str(p.id),
            "product": p.product_name,
            "competitor": p.competitor.name if p.competitor else None,
            "brand": p.brand.name if p.brand else None,
            "outlet": p.retailer.name if p.retailer else None,
            "channel_type": p.retailer.channel_type if p.retailer else None,
            "pack_size": p.pack_size,
            "pack_grams": g,
            "promotion_type": p.promotion_type,
            "effective_pack_price": c_price,
            "price_per_100g": c_unit,
            "gap_vs_candidate_pct": gap_vs_candidate,
            "gap_vs_baseline_pct": gap_vs_baseline,
            "undercuts_candidate": undercuts_cand,
            "undercuts_baseline": undercuts_base,
        })

    comparable_matches.sort(key=lambda m: m["price_per_100g"])
    total_comparable = len(comparable_matches)

    projected_undercut_count = sum(1 for m in comparable_matches if m["undercuts_candidate"])
    projected_cheaper_than_count = sum(1 for m in comparable_matches if m["price_per_100g"] > candidate_per_100g)
    projected_rank = projected_undercut_count + 1

    current_undercut_count = sum(1 for m in comparable_matches if m["undercuts_baseline"]) if baseline_effective_unit else 0
    current_rank = (current_undercut_count + 1) if baseline_effective_unit else None
    rank_change = (current_rank - projected_rank) if current_rank is not None else None
    undercut_change = projected_undercut_count - current_undercut_count

    if total_comparable == 0:
        market_pos = "NO_COMPETITORS"
    elif projected_rank == 1:
        market_pos = "CHEAPEST_IN_MARKET"
    elif projected_rank <= max(1, total_comparable * 0.25):
        market_pos = "TOP_QUARTILE_COMPETITIVE"
    elif projected_rank <= max(1, total_comparable * 0.50):
        market_pos = "MID_MARKET"
    else:
        market_pos = "PREMIUM_TIER"

    eliminated = [
        m for m in comparable_matches
        if m["undercuts_baseline"] and not m["undercuts_candidate"]
    ]
    remaining = [
        m for m in comparable_matches
        if m["undercuts_candidate"]
    ]

    min_comp_unit = min(comp_units) if comp_units else None
    target_pack_price_rank_1 = round(min_comp_unit * prod_pack_grams / 100.0, 2) if min_comp_unit else None

    if current_rank is not None:
        summary_text = (
            f"At candidate price Rp {candidate_effective_pack:,.0f} (Rp {candidate_per_100g:,.2f}/100g), "
            f"market rank moves from #{current_rank} to #{projected_rank} of {total_comparable + 1}. "
            f"Undercuts change by {undercut_change:+d} ({current_undercut_count} -> {projected_undercut_count}), "
            f"eliminating undercuts from {len(eliminated)} competitor promotions."
        )
    else:
        summary_text = (
            f"At candidate price Rp {candidate_effective_pack:,.0f} (Rp {candidate_per_100g:,.2f}/100g), "
            f"product ranks #{projected_rank} of {total_comparable + 1} with {projected_undercut_count} undercutting competitors."
        )

    return {
        "simulated_product": {
            "id": str(product.id) if product else None,
            "name": prod_name,
            "sku": getattr(product, "sku", None),
            "category": prod_category,
            "pack_size": prod_pack_size,
            "pack_grams": prod_pack_grams,
            "candidate_effective_pack_price": candidate_effective_pack,
            "candidate_price_per_100g": candidate_per_100g,
            "candidate_promo_type": candidate_promo_type,
            "candidate_discount_percentage": candidate_discount_percentage,
        },
        "current_baseline": {
            "regular_price": base_regular_price,
            "regular_price_per_100g": current_reg_unit,
            "promo_price": current_promo_pack,
            "promo_price_per_100g": current_promo_unit,
            "has_active_promo": curr_has_promo,
            "undercut_count": current_undercut_count,
            "market_rank": current_rank,
        } if product else None,
        "projected_position": {
            "market_rank": projected_rank,
            "total_comparable": total_comparable,
            "market_position": market_pos,
            "current_rank": current_rank,
            "rank_change": rank_change,
            "current_undercut_count": current_undercut_count,
            "projected_undercut_count": projected_undercut_count,
            "undercut_change": undercut_change,
            "cheaper_than_count": projected_cheaper_than_count,
            "target_unit_price_for_rank_1": min_comp_unit,
            "target_pack_price_for_rank_1": target_pack_price_rank_1,
        },
        "impact_summary": summary_text,
        "eliminated_undercuts": eliminated,
        "remaining_undercuts": remaining,
        "comparable_promotions": comparable_matches[:MAX_MATCHES * 2],
    }
