from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.models.own_product import OwnProduct
from app.services.comparison import (
    CATEGORIES,
    build_aggregations,
    build_comparison,
    calculate_gap_pct,
    effective_pack_price,
    is_product_match,
    is_valid_active_promotion,
    parse_pack_grams,
    parse_price,
    per_100g,
    simulate_price,
)


def test_comparison_summary_uses_all_matches_and_reports_coverage(monkeypatch):
    now = datetime(2026, 11, 19, tzinfo=timezone.utc)
    db = MagicMock()
    catalog = db.query.return_value.filter.return_value.order_by.return_value
    catalog.all.return_value = [
        OwnProduct(name="Matched", category="BISCUIT", regular_price=12000, pack_size="300g"),
        OwnProduct(name="Unmatched", category="WAFER", regular_price=12000, pack_size="300g"),
    ]
    shortlist = db.query.return_value.outerjoin.return_value.outerjoin.return_value.outerjoin.return_value.options
    promotions = shortlist.return_value.filter.return_value.filter.return_value
    promotions.all.return_value = [
        promo(
            id=price, product_name="Comparable biscuit", sku=None, category="BISCUIT", pack_size="300g",
            promo_price=price, brand=None, competitor=None, retailer=None, status="ACTIVE",
            start_date=None, end_date=None, last_verified_at=now,
        )
        for price in (6000, 12000, 18000)
    ]
    monkeypatch.setattr("app.services.comparison.MAX_MATCHES", 1)

    result = build_comparison(db, now=now)
    summary = result["summary"]
    assert result["products"][0]["comparable_total"] == 3
    assert len(result["products"][0]["comparable"]) == 1
    assert summary["price_index_vs_market"] == 100
    assert summary["pct_under_pressure"] == 100
    assert summary["comparable_products"] == summary["not_comparable"] == 1
    assert summary["deepest_discount_by_category"] == {}

    promotions.all.return_value = []
    summary = build_comparison(db, now=now)["summary"]
    assert summary["price_index_vs_market"] is None
    assert summary["price_index_gap_pct"] is None
    assert summary["pct_under_pressure"] is None
    assert summary["comparable_products"] == 0


@pytest.mark.parametrize("text,expected", [
    ("300g", 300), ("300 g", 300), ("300 gr", 300), ("1kg", 1000), ("1,5 kg", 1500), ("0.5 kg", 500),
    ("12x25g", 300), ("2 x 150 gram", 300), ("Roma Kelapa 300G", 300),
    (None, None), ("", None), ("24 pcs", None), ("500ml", None),
])
def test_parse_pack_grams(text, expected):
    assert parse_pack_grams(text) == expected


@pytest.mark.parametrize("text,expected", [
    (12500, 12500), ("12500", 12500), ("12.500", 12500), ("Rp 12.500", 12500), ("Rp12.500,50", 12500.5),
    ("12,5", 12.5), ("1.250.000", 1250000),
])
def test_parse_price(text, expected):
    assert parse_price(text) == pytest.approx(expected)


@pytest.mark.parametrize("bad", ["", "abc", "0", "-5", "99999999999", None])
def test_parse_price_rejects_bad_values(bad):
    with pytest.raises(ValueError):
        parse_price(bad)


def promo(**kw):
    base = dict(promo_price=None, regular_price=None, discount_percentage=None, promotion_type="DISCOUNT",
                buy_quantity=None, free_quantity=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_effective_price_uses_promo_price_or_discount():
    assert effective_pack_price(promo(promo_price=7000)) == 7000
    assert effective_pack_price(promo(regular_price=10000, discount_percentage=30)) == 7000
    assert effective_pack_price(promo(discount_percentage=30)) is None        # no price to discount
    assert effective_pack_price(promo()) is None


def test_effective_price_for_buy_x_get_y():
    # Buy 2 get 1 free at 9,000 each -> you pay for 2 of 3 packs -> 6,000 per pack
    p = promo(promo_price=9000, promotion_type="BUY_X_GET_Y", buy_quantity=2, free_quantity=1)
    assert effective_pack_price(p) == 6000


def test_per_100g():
    assert per_100g(7000, 300) == 2333.33
    assert per_100g(7000, None) is None
    assert per_100g(None, 300) is None
    assert per_100g(7000, 0) is None


def test_effective_price_dual_state():
    # Regular price check
    p = promo(regular_price=12000, promo_price=9000)
    assert effective_pack_price(p, price_type="regular") == 12000
    assert effective_pack_price(p, price_type="promo") == 9000

    # Deriving regular price from promo_price and discount
    p2 = promo(promo_price=7000, discount_percentage=30)
    assert effective_pack_price(p2, price_type="regular") == 10000.0
    assert effective_pack_price(p2, price_type="promo") == 7000.0

    # BUY_X_GET_Y dual-state
    p3 = promo(regular_price=12000, promo_price=9000, promotion_type="BUY_X_GET_Y", buy_quantity=2, free_quantity=1)
    assert effective_pack_price(p3, price_type="regular") == 12000
    assert effective_pack_price(p3, price_type="promo") == 6000


def test_per_100g_dual_state_and_objects():
    p = promo(regular_price=12000, promo_price=9000, pack_size="300g")
    assert per_100g(p, price_type="regular") == 4000.0
    assert per_100g(p, price_type="promo") == 3000.0

    # Dict input support
    d = {"regular_price": 15000, "promo_price": 10500, "pack_size": "300g"}
    assert per_100g(d, price_type="regular") == 5000.0
    assert per_100g(d, price_type="promo") == 3500.0


def test_calculate_gap_pct():
    # Negative gap means competitor is cheaper
    assert calculate_gap_pct(3000, 4000) == -25.0
    # Positive gap means competitor is dearer
    assert calculate_gap_pct(5000, 4000) == 25.0
    # Equal prices
    assert calculate_gap_pct(4000, 4000) == 0.0
    # None handling
    assert calculate_gap_pct(None, 4000) is None
    assert calculate_gap_pct(3000, None) is None
    assert calculate_gap_pct(3000, 0) is None


def test_is_product_match_categories():
    own = SimpleNamespace(category="BISCUIT", sku=None, brand=None)
    for cat in ("BISCUIT", "CRACKER", "COOKIE", "WAFER", "SNACK"):
        assert cat in CATEGORIES
        p_match = SimpleNamespace(category=cat.lower(), sku=None, brand=None, competitor=None)
        p_mismatch = SimpleNamespace(category="BEVERAGE", sku=None, brand=None, competitor=None)
        assert is_product_match(SimpleNamespace(category=cat, sku=None, brand=None), p_match, own_grams=300, promo_grams=300) is True
        assert is_product_match(SimpleNamespace(category=cat, sku=None, brand=None), p_mismatch, own_grams=300, promo_grams=300) is False


def test_is_product_match_pack_ratio():
    own = SimpleNamespace(category="BISCUIT", sku=None, brand=None)
    promo_obj = SimpleNamespace(category="BISCUIT", sku=None, brand=None, competitor=None)

    # 300g baseline: ratio between 0.5x (150g) and 2.0x (600g)
    assert is_product_match(own, promo_obj, own_grams=300, promo_grams=150) is True
    assert is_product_match(own, promo_obj, own_grams=300, promo_grams=600) is True
    assert is_product_match(own, promo_obj, own_grams=300, promo_grams=300) is True

    # Outside bounds
    assert is_product_match(own, promo_obj, own_grams=300, promo_grams=149) is False
    assert is_product_match(own, promo_obj, own_grams=300, promo_grams=601) is False
    assert is_product_match(own, promo_obj, own_grams=300, promo_grams=None) is False
    assert is_product_match(own, promo_obj, own_grams=None, promo_grams=300) is False


def test_is_product_match_direct_sku_and_brand_mappings():
    own = SimpleNamespace(category="BISCUIT", sku="SKU-1", brand="MyBrand")
    promo_sku1 = SimpleNamespace(category="BISCUIT", sku="COMP-1", brand=SimpleNamespace(name="CompBrand"), competitor=None)
    promo_sku2 = SimpleNamespace(category="BISCUIT", sku="COMP-2", brand=SimpleNamespace(name="OtherBrand"), competitor=None)

    # Direct SKU mappings
    sku_map = {"SKU-1": ["COMP-1"]}
    assert is_product_match(own, promo_sku1, own_grams=300, promo_grams=300, sku_mappings=sku_map) is True
    assert is_product_match(own, promo_sku2, own_grams=300, promo_grams=300, sku_mappings=sku_map) is False

    # Direct Brand mappings
    brand_map = {"MyBrand": ["CompBrand"]}
    assert is_product_match(own, promo_sku1, own_grams=300, promo_grams=300, brand_mappings=brand_map) is True
    assert is_product_match(own, promo_sku2, own_grams=300, promo_grams=300, brand_mappings=brand_map) is False


def test_is_valid_active_promotion():
    now = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)

    # 1. Valid active dated promotion
    p_valid = SimpleNamespace(
        status="ACTIVE",
        has_open_conflict=False,
        start_date=now - timedelta(days=2),
        end_date=now + timedelta(days=5),
        last_verified_at=now - timedelta(days=1),
        last_seen_at=now - timedelta(days=1),
    )
    assert is_valid_active_promotion(p_valid, now) is True

    # 2. Future promotion (not yet active)
    p_future = SimpleNamespace(
        status="ACTIVE",
        has_open_conflict=False,
        start_date=now + timedelta(days=1),
        end_date=now + timedelta(days=10),
        last_verified_at=now,
        last_seen_at=now,
    )
    assert is_valid_active_promotion(p_future, now) is False

    # 3. Expired promotion
    p_expired = SimpleNamespace(
        status="ACTIVE",
        has_open_conflict=False,
        start_date=now - timedelta(days=10),
        end_date=now - timedelta(days=1),
        last_verified_at=now,
        last_seen_at=now,
    )
    assert is_valid_active_promotion(p_expired, now) is False

    # 4. Unstated dates within 14 days threshold
    p_unstated_recent = SimpleNamespace(
        status="ACTIVE",
        has_open_conflict=False,
        start_date=None,
        end_date=None,
        last_verified_at=now - timedelta(days=7),
        last_seen_at=now - timedelta(days=7),
    )
    assert is_valid_active_promotion(p_unstated_recent, now, unstated_recency_days=14) is True

    # 5. Unstated dates older than threshold (e.g. 15 days ago)
    p_unstated_stale = SimpleNamespace(
        status="ACTIVE",
        has_open_conflict=False,
        start_date=None,
        end_date=None,
        last_verified_at=now - timedelta(days=15),
        last_seen_at=now - timedelta(days=15),
    )
    assert is_valid_active_promotion(p_unstated_stale, now, unstated_recency_days=14) is False

    # 6. Status inactive or open conflict
    p_inactive = SimpleNamespace(
        status="EXPIRED",
        has_open_conflict=False,
        start_date=now - timedelta(days=2),
        end_date=now + timedelta(days=2),
        last_verified_at=now,
        last_seen_at=now,
    )
    assert is_valid_active_promotion(p_inactive, now) is False

    p_conflict = SimpleNamespace(
        status="ACTIVE",
        has_open_conflict=True,
        start_date=now - timedelta(days=2),
        end_date=now + timedelta(days=2),
        last_verified_at=now,
        last_seen_at=now,
    )
    assert is_valid_active_promotion(p_conflict, now) is False


def test_build_aggregations():
    now = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)
    own_prod = SimpleNamespace(
        id="own-1", category="BISCUIT", pack_size="300g", pack_grams=300,
        regular_price=12000, promo_price=None, has_active_promo=False
    )

    p1 = SimpleNamespace(
        id="p1", category="BISCUIT", promotion_type="DISCOUNT", discount_percentage=25,
        brand=SimpleNamespace(name="Oreo"), competitor=SimpleNamespace(name="Mondelez"),
        retailer=SimpleNamespace(name="Indomaret", channel_type="MINIMARKET")
    )
    p2 = SimpleNamespace(
        id="p2", category="BISCUIT", promotion_type="BUY_X_GET_Y", discount_percentage=None,
        brand=SimpleNamespace(name="Roma"), competitor=SimpleNamespace(name="Mayora"),
        retailer=SimpleNamespace(name="Superindo", channel_type="SUPERMARKET")
    )
    p3 = SimpleNamespace(
        id="p3", category="WAFER", promotion_type="DISCOUNT", discount_percentage=15,
        brand=SimpleNamespace(name="Tango"), competitor=SimpleNamespace(name="OT"),
        retailer=SimpleNamespace(name="Alfamart", channel_type="MINIMARKET")
    )

    # tuple: (p, grams, promo_price, promo_unit, reg_price, reg_unit)
    candidates = [
        (p1, 300, 9000, 3000.0, 12000, 4000.0),    # undercuts 12000 (4000/100g)
        (p2, 300, 6000, 2000.0, 9000, 3000.0),     # undercuts 12000 (4000/100g)
        (p3, 150, 7500, 5000.0, 9000, 6000.0),     # WAFER (no own product in WAFER)
    ]

    aggs = build_aggregations(candidates, [own_prod])
    assert aggs["total_active_promotions"] == 3

    # Check by_brand
    brands = {b["brand"]: b for b in aggs["by_brand"]}
    assert "Oreo" in brands and brands["Oreo"]["count"] == 1 and brands["Oreo"]["undercut_count"] == 1
    assert "Roma" in brands and brands["Roma"]["count"] == 1 and brands["Roma"]["undercut_count"] == 1
    assert "Tango" in brands and brands["Tango"]["count"] == 1 and brands["Tango"]["undercut_count"] == 0

    # Check by_retailer
    retailers = {r["retailer"]: r for r in aggs["by_retailer"]}
    assert "Indomaret" in retailers and retailers["Indomaret"]["channel_type"] == "MINIMARKET"
    assert "Superindo" in retailers and retailers["Superindo"]["channel_type"] == "SUPERMARKET"
    assert "Alfamart" in retailers and retailers["Alfamart"]["channel_type"] == "MINIMARKET"

    # Check by_category
    cats = {c["category"]: c for c in aggs["by_category"]}
    assert "BISCUIT" in cats and cats["BISCUIT"]["count"] == 2 and cats["BISCUIT"]["undercut_count"] == 2
    assert "WAFER" in cats and cats["WAFER"]["count"] == 1

    # Check by_mechanic
    mechs = {m["mechanic"]: m for m in aggs["by_mechanic"]}
    assert "DISCOUNT" in mechs and mechs["DISCOUNT"]["count"] == 2
    assert "BUY_X_GET_Y" in mechs and mechs["BUY_X_GET_Y"]["count"] == 1


def test_simulate_price_validation():
    from unittest.mock import MagicMock
    mock_db = MagicMock()
    mock_db.get.return_value = None

    # 1. Product not found
    with pytest.raises(ValueError, match="not found"):
        simulate_price(mock_db, product_id="11111111-1111-1111-1111-111111111111")

    # 2. Missing pack grams / size
    with pytest.raises(ValueError, match="Pack size in grams"):
        simulate_price(mock_db, name="Test", regular_price=10000, pack_size=None)

    # 3. Missing price
    with pytest.raises(ValueError, match="valid candidate price"):
        simulate_price(mock_db, name="Test", pack_size="300g", candidate_price=None, regular_price=None)
