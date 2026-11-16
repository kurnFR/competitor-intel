"""Unit tests for Shrinkflation detection."""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.services.shrinkflation import _normalize_name_for_grouping, detect_shrinkflation


def test_normalize_name():
    assert _normalize_name_for_grouping("Oreo Vanilla 133g") == "oreo vanilla"
    assert _normalize_name_for_grouping("Tango Wafer Cokelat 176 gr") == "tango wafer cokelat"
    assert _normalize_name_for_grouping("Roma Malkist Abon 135 g Promo Hemat") == "roma malkist abon"


def test_detect_shrinkflation_with_mock_db():
    now = datetime.now(timezone.utc)

    # Competitor & brand mock
    comp = MagicMock()
    comp.name = "Mondelez"
    brand = MagicMock()
    brand.name = "Oreo"
    ret = MagicMock()
    ret.name = "Indomaret"

    # Baseline 1: 150g for Rp 10.000 (Unit: ~Rp 66.67 / 100g)
    p_old = MagicMock()
    p_old.competitor = comp
    p_old.brand = brand
    p_old.retailer = ret
    p_old.product_name = "Oreo Original 150g"
    p_old.pack_size = "150g"
    p_old.regular_price = 10000.0
    p_old.promo_price = 10000.0
    p_old.category = "COOKIE"
    p_old.first_seen_at = now - timedelta(days=60)

    # Observation 2: 133g for Rp 10.000 (Unit: ~Rp 75.19 / 100g -> +12.8% inflation!)
    p_new = MagicMock()
    p_new.competitor = comp
    p_new.brand = brand
    p_new.retailer = ret
    p_new.product_name = "Oreo Original 133g"
    p_new.pack_size = "133g"
    p_new.regular_price = 10000.0
    p_new.promo_price = 10000.0
    p_new.category = "COOKIE"
    p_new.first_seen_at = now - timedelta(days=5)

    mock_db = MagicMock()
    # Mock chain db.query().outerjoin().outerjoin().outerjoin().filter().order_by().all()
    mock_db.query.return_value.outerjoin.return_value.outerjoin.return_value.outerjoin.return_value.filter.return_value.order_by.return_value.all.return_value = [
        p_old,
        p_new,
    ]

    events = detect_shrinkflation(mock_db, days=90, min_downsize_pct=5.0, now=now)
    assert len(events) == 1
    ev = events[0]
    assert ev["competitor"] == "Mondelez"
    assert ev["brand"] == "Oreo"
    assert ev["old_grams"] == 150.0
    assert ev["new_grams"] == 133.0
    assert ev["downsize_grams"] == 17.0
    assert ev["downsize_pct"] == 11.3
    assert ev["unit_price_inflation_pct"] > 10.0
