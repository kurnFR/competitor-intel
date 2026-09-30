from types import SimpleNamespace

import pytest

from app.services.comparison import effective_pack_price, parse_pack_grams, parse_price, per_100g


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
