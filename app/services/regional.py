"""Regional price comparison (PRD 10): the same product's price per region, never collapsed into one number."""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, List

from app.services.comparison import effective_pack_price, parse_pack_grams, per_100g
from app.services.geography import REGION_LABELS, UNKNOWN

REGION_ORDER = ["NATIONAL", "JABODETABEK", "JAWA", "SUMATERA", "KALIMANTAN", "SULAWESI", "BALI_NUSRA", "MALUKU", "PAPUA",
                "ONLINE", "STORE_SPECIFIC", "MULTI_REGION", "UNMAPPED"]


def _key(p: Any) -> str:
    name = re.sub(r"[^a-z0-9]+", " ", (p.product_name or "").lower()).strip()
    pack = re.sub(r"[^a-z0-9]+", "", (p.pack_size or "").lower())
    return f"{name}|{pack}"


def build_regional_prices(promotions: List[Any]) -> Dict[str, Any]:
    """Group eligible promotions by product, then by stated region.

    Promotions whose region is not stated are shown separately ("Not stated") and are never counted as nationwide
    or merged into a region. Only promotions with a computable price are shown.
    """
    groups: Dict[str, Dict[str, Any]] = {}
    for p in promotions:
        price = effective_pack_price(p)
        if price is None:
            continue
        g = groups.setdefault(_key(p), {
            "product": p.product_name, "brand": p.brand.name if p.brand else None, "pack_size": p.pack_size,
            "category": p.category, "competitor": p.competitor.name if p.competitor else None, "regions": defaultdict(list)})
        region = p.geography_region or UNKNOWN
        g["regions"][region].append({
            "promotion_id": str(p.id), "price": price, "outlet": p.retailer.name if p.retailer else None,
            "promotion_type": p.promotion_type, "wording": p.geography,
            "valid_until": p.end_date.strftime("%Y-%m-%d") if p.end_date else None,
        })

    products = []
    present_regions = set()
    for g in groups.values():
        cells = {}
        for region, rows in g["regions"].items():
            prices = [r["price"] for r in rows]
            grams = parse_pack_grams(g["pack_size"])
            cells[region] = {
                "label": REGION_LABELS.get(region, region), "min_price": min(prices), "max_price": max(prices),
                "price_per_100g": per_100g(min(prices), grams), "count": len(rows),
                "outlets": sorted({r["outlet"] for r in rows if r["outlet"]}),
                "wording": sorted({r["wording"] for r in rows if r["wording"]}),
                "promotion_ids": [r["promotion_id"] for r in rows],
            }
            if region != UNKNOWN:
                present_regions.add(region)
        stated = {r: c["min_price"] for r, c in cells.items() if r != UNKNOWN}
        spread = None
        if len(stated) >= 2:
            lo, hi = min(stated.values()), max(stated.values())
            spread = round((hi - lo) / lo * 100.0, 1) if lo > 0 else None
        products.append({
            "product": g["product"], "brand": g["brand"], "pack_size": g["pack_size"], "category": g["category"],
            "competitor": g["competitor"], "cells": cells, "regions_compared": len(stated), "spread_pct": spread,
            "differs_by_region": bool(spread and spread > 0),
        })
    # Products that differ by region first, widest gap first; then multi-region products; then the rest.
    products.sort(key=lambda x: (-(x["spread_pct"] or 0), -x["regions_compared"], (x["product"] or "").lower()))
    ordered = [r for r in REGION_ORDER if r in present_regions] + sorted(present_regions - set(REGION_ORDER))
    return {
        "regions": [{"code": r, "label": REGION_LABELS.get(r, r)} for r in ordered],
        "summary": {"products": len(products), "differ_by_region": sum(1 for x in products if x["differs_by_region"]),
                    "with_unstated_region": sum(1 for x in products if UNKNOWN in x["cells"])},
        "products": products,
    }
