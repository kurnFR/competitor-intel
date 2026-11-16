import pytest
from app.services.campaigns import (
    detect_campaign_tags,
    get_campaign_tag_codes,
    get_available_campaigns,
    CAMPAIGNS,
)


def test_available_campaigns():
    campaigns = get_available_campaigns()
    assert len(campaigns) >= 8
    codes = {c["code"] for c in campaigns}
    assert "RAMADHAN_LEBARAN" in codes
    assert "JSM_WEEKEND" in codes
    assert "GAJIAN_PAYDAY" in codes
    assert "BOGO" in codes
    assert "CASHBACK_EWALLET" in codes


def test_detect_ramadhan_festive():
    data = {
        "product_name": "Khong Guan Biscuit Assorted Kaleng 1600g",
        "promotion_title": "Spesial Berkah Ramadhan dan Lebaran",
        "promotion_type": "DISCOUNT",
    }
    tags = detect_campaign_tags(data)
    codes = [t["code"] for t in tags]
    assert "RAMADHAN_LEBARAN" in codes
    tag = next(t for t in tags if t["code"] == "RAMADHAN_LEBARAN")
    assert tag["color"] == "emerald"
    assert "Ramadhan" in tag["label"]


def test_detect_jsm_weekend():
    data = {
        "product_name": "Oreo Vanilla 133g",
        "evidence_quote": "Katalog Promo JSM Indomaret Jumat Sabtu Minggu",
        "promotion_type": "DISCOUNT",
    }
    codes = get_campaign_tag_codes(data)
    assert "JSM_WEEKEND" in codes


def test_detect_payday_gajian():
    data = {
        "product_name": "Tango Wafer Cokelat 176g",
        "promotion_description": "Super Hemat Promo Gajian Awal Bulan",
        "promotion_type": "DISCOUNT",
    }
    codes = get_campaign_tag_codes(data)
    assert "GAJIAN_PAYDAY" in codes


def test_detect_bogo_by_type_and_text():
    # By promotion type
    promo1 = {"product_name": "Roma Kelapa 300g", "promotion_type": "BUY_X_GET_Y", "buy_quantity": 1}
    assert "BOGO" in get_campaign_tag_codes(promo1)

    # By text keyword
    promo2 = {"product_name": "Roma Malkist Beli 1 Gratis 1", "promotion_type": "DISCOUNT"}
    assert "BOGO" in get_campaign_tag_codes(promo2)


def test_detect_cashback_ewallet():
    promo1 = {"product_name": "Monde Butter Cookies 454g", "cashback_amount": 5000}
    assert "CASHBACK_EWALLET" in get_campaign_tag_codes(promo1)

    promo2 = {"product_name": "Oreo Soft Cake", "evidence_quote": "Ekstra Cashback Rp2.000 bayar pakai GoPay"}
    assert "CASHBACK_EWALLET" in get_campaign_tag_codes(promo2)


def test_detect_multiple_tags():
    data = {
        "product_name": "Nissin Wafer Chocolate Kaleng 570g",
        "promotion_title": "Promo JSM Akhir Pekan Sambut Ramadhan Berkah",
        "promotion_type": "BUY_X_GET_Y",
        "buy_quantity": 2,
    }
    codes = get_campaign_tag_codes(data)
    assert "RAMADHAN_LEBARAN" in codes
    assert "JSM_WEEKEND" in codes
    assert "BOGO" in codes


def test_no_false_positive():
    data = {
        "product_name": "Plain Plain Biscuit 100g",
        "promotion_type": "DISCOUNT",
        "evidence_quote": "Harga promo Rp 5.000",
    }
    tags = detect_campaign_tags(data)
    assert len(tags) == 0
