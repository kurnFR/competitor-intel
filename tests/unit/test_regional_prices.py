from datetime import datetime, timezone
from types import SimpleNamespace

from app.services.regional import build_regional_prices


def promo(name, region, price, pack="300g", wording=None, outlet="Indomaret", **kw):
    base = dict(id=f"{name}-{region}-{price}", product_name=name, pack_size=pack, category="BISCUIT", promo_price=price,
                regular_price=None, discount_percentage=None, promotion_type="DISCOUNT", buy_quantity=None, free_quantity=None,
                geography_region=region, geography=wording, end_date=None, brand=None, competitor=SimpleNamespace(name="Mayora"),
                retailer=SimpleNamespace(name=outlet))
    base.update(kw)
    return SimpleNamespace(**base)


def test_prices_are_kept_per_region_and_never_merged():
    data = build_regional_prices([
        promo("Roma Kelapa", "JAWA", 7900, wording="Jawa"), promo("Roma Kelapa", "SUMATERA", 8500, wording="Sumatera"),
        promo("Roma Kelapa", "KALIMANTAN", 9500), promo("Roma Kelapa", "SULAWESI", 9900),
    ])
    assert [r["code"] for r in data["regions"]] == ["JAWA", "SUMATERA", "KALIMANTAN", "SULAWESI"]
    (product,) = data["products"]
    assert {r: c["min_price"] for r, c in product["cells"].items()} == {"JAWA": 7900, "SUMATERA": 8500, "KALIMANTAN": 9500, "SULAWESI": 9900}
    assert product["spread_pct"] == 25.3 and product["differs_by_region"] is True and product["regions_compared"] == 4


def test_unstated_region_is_separate_and_never_nationwide():
    data = build_regional_prices([promo("Roma", "UNKNOWN", 7000), promo("Roma", "JAWA", 7900)])
    (product,) = data["products"]
    assert "UNKNOWN" in product["cells"] and "NATIONAL" not in product["cells"]
    assert [r["code"] for r in data["regions"]] == ["JAWA"]            # UNKNOWN is not a region column
    assert product["regions_compared"] == 1 and product["spread_pct"] is None   # one stated region -> nothing to compare
    assert data["summary"]["with_unstated_region"] == 1


def test_different_pack_sizes_are_different_products():
    data = build_regional_prices([promo("Roma", "JAWA", 7000, pack="300g"), promo("Roma", "JAWA", 3500, pack="150g")])
    assert len(data["products"]) == 2


def test_promotions_without_a_computable_price_are_left_out():
    data = build_regional_prices([promo("Roma", "JAWA", None)])
    assert data["products"] == [] and data["regions"] == []


def test_multiple_promotions_in_one_region_show_the_range_and_outlets():
    data = build_regional_prices([promo("Roma", "JAWA", 7000, outlet="Indomaret"), promo("Roma", "JAWA", 7600, outlet="Alfamart")])
    cell = data["products"][0]["cells"]["JAWA"]
    assert (cell["min_price"], cell["max_price"], cell["count"]) == (7000, 7600, 2)
    assert cell["outlets"] == ["Alfamart", "Indomaret"]


def test_buy_x_get_y_uses_the_effective_price():
    data = build_regional_prices([promo("Roma", "JAWA", 9000, promotion_type="BUY_X_GET_Y", buy_quantity=2, free_quantity=1)])
    assert data["products"][0]["cells"]["JAWA"]["min_price"] == 6000


def test_products_priced_differently_sort_first():
    data = build_regional_prices([
        promo("Same everywhere", "JAWA", 5000), promo("Same everywhere", "SUMATERA", 5000),
        promo("Differs", "JAWA", 5000), promo("Differs", "SUMATERA", 7000), promo("Single region", "JAWA", 1000),
    ])
    assert [p["product"] for p in data["products"]] == ["Differs", "Same everywhere", "Single region"]
    assert data["summary"]["differ_by_region"] == 1
