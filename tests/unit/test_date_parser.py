from datetime import date
import pytest

from app.services.extraction.date_parser import (
    extract_banner_validity,
    extract_pack_size_from_name,
    parse_indonesian_date,
    parse_indonesian_date_range,
    sanitize_price,
)


def test_parse_indonesian_date_single():
    assert parse_indonesian_date("2026-05-12") == date(2026, 5, 12)
    assert parse_indonesian_date("12 Mei 2026") == date(2026, 5, 12)
    assert parse_indonesian_date("12-Mei-2026") == date(2026, 5, 12)
    assert parse_indonesian_date("05 Januari 2026") == date(2026, 1, 5)
    assert parse_indonesian_date("31 Des 2025") == date(2025, 12, 31)
    assert parse_indonesian_date("1 Okt 2026") == date(2026, 10, 1)
    assert parse_indonesian_date("12/05/2026") == date(2026, 5, 12)
    assert parse_indonesian_date("12.05.2026") == date(2026, 5, 12)
    assert parse_indonesian_date("12-05-2026") == date(2026, 5, 12)
    assert parse_indonesian_date("s/d 15 Mei 2026") == date(2026, 5, 15)
    assert parse_indonesian_date("sampai 15 Mei 2026") == date(2026, 5, 15)
    assert parse_indonesian_date("12 Mei", default_year=2026) == date(2026, 5, 12)


def test_parse_indonesian_date_range_same_month():
    assert parse_indonesian_date_range("12 - 14 Mei 2026") == ("2026-05-12", "2026-05-14")
    assert parse_indonesian_date_range("12-14 Mei 2026") == ("2026-05-12", "2026-05-14")
    assert parse_indonesian_date_range("1 - 15 Oktober 2026") == ("2026-10-01", "2026-10-15")
    assert parse_indonesian_date_range("01 s/d 15 Maret 2026") == ("2026-03-01", "2026-03-15")
    assert parse_indonesian_date_range("1 s.d. 15 Maret 2026") == ("2026-03-01", "2026-03-15")
    assert parse_indonesian_date_range("1 sampai 15 Maret 2026") == ("2026-03-01", "2026-03-15")


def test_parse_indonesian_date_range_cross_month():
    assert parse_indonesian_date_range("28 Oktober - 3 November 2026") == ("2026-10-28", "2026-11-03")
    assert parse_indonesian_date_range("28 Okt - 03 Nov 2026") == ("2026-10-28", "2026-11-03")
    assert parse_indonesian_date_range("28 Nov s/d 4 Des 2026") == ("2026-11-28", "2026-12-04")


def test_parse_indonesian_date_range_cross_year():
    assert parse_indonesian_date_range("28 Des 2025 - 5 Jan 2026") == ("2025-12-28", "2026-01-05")
    assert parse_indonesian_date_range("28 Des - 3 Jan 2026") == ("2025-12-28", "2026-01-03")
    assert parse_indonesian_date_range("25 Desember 2025 s/d 05 Januari 2026") == ("2025-12-25", "2026-01-05")


def test_parse_indonesian_date_range_banner_prefixes():
    assert parse_indonesian_date_range("Periode: 12 - 14 Mei 2026") == ("2026-05-12", "2026-05-14")
    assert parse_indonesian_date_range("Berlaku 12 - 14 Mei 2026") == ("2026-05-12", "2026-05-14")
    assert parse_indonesian_date_range("Promo JSM 24 - 26 Juli 2026") == ("2026-07-24", "2026-07-26")
    assert parse_indonesian_date_range("Katalog Super Hemat Edisi 23 Periode 28 Oktober - 3 November 2026") == ("2026-10-28", "2026-11-03")
    assert parse_indonesian_date_range("Promo Koran Superindo 16 - 22 Mei 2026") == ("2026-05-16", "2026-05-22")


def test_parse_indonesian_date_range_multi_week():
    assert parse_indonesian_date_range("Minggu ke-1: 1 - 7 Juni 2026") == ("2026-06-01", "2026-06-07")
    assert parse_indonesian_date_range("Week 1 (1 - 7 Nov 2026)") == ("2026-11-01", "2026-11-07")
    assert parse_indonesian_date_range("Minggu 2: 8 - 14 Nov 2026") == ("2026-11-08", "2026-11-14")
    assert parse_indonesian_date_range("Minggu 1 & 2: 1 - 14 Nov 2026") == ("2026-11-01", "2026-11-14")
    assert parse_indonesian_date_range("Periode 1 - 21 Nov 2026 (Minggu 1-3)") == ("2026-11-01", "2026-11-21")
    assert parse_indonesian_date_range("EDISI MINGGUAN PERIODE 12 - 18 MEI 2026") == ("2026-05-12", "2026-05-18")


def test_parse_indonesian_date_range_numeric_and_single_end():
    assert parse_indonesian_date_range("12/05/2026 - 14/05/2026") == ("2026-05-12", "2026-05-14")
    assert parse_indonesian_date_range("12.05.2026 s/d 14.05.2026") == ("2026-05-12", "2026-05-14")
    assert parse_indonesian_date_range("s/d 15 Mei 2026") == (None, "2026-05-15")


def test_extract_banner_validity():
    payload1 = {"validity_period": "12 - 14 Mei 2026", "promotions": []}
    assert extract_banner_validity(payload1) == ("2026-05-12", "2026-05-14")

    payload2 = {"banner_date": "Periode 28 Okt - 03 Nov 2026", "promotions": []}
    assert extract_banner_validity(payload2) == ("2026-10-28", "2026-11-03")

    payload3 = {"start_date": "12 Mei 2026", "end_date": "14 Mei 2026"}
    assert extract_banner_validity(payload3) == ("2026-05-12", "2026-05-14")

    payload4 = {"start_date": "12 - 14 Mei 2026"}
    assert extract_banner_validity(payload4) == ("2026-05-12", "2026-05-14")


def test_parse_indonesian_date_range_duration_phrases():
    assert parse_indonesian_date_range("Berlaku 2 minggu mulai 1 Mei 2026") == ("2026-05-01", "2026-05-14")
    assert parse_indonesian_date_range("Berlaku 3 hari mulai 12 Mei 2026") == ("2026-05-12", "2026-05-14")
    assert parse_indonesian_date_range("Periode 2 Minggu (1 - 14 Mei 2026)") == ("2026-05-01", "2026-05-14")
    assert parse_indonesian_date_range("Promo 2 Pekan: 1 - 14 Mei 2026") == ("2026-05-01", "2026-05-14")


def test_parse_indonesian_date_range_cross_year_omitted_year():
    assert parse_indonesian_date_range("28 Des - 4 Jan", default_year=2026) == ("2026-12-28", "2027-01-04")
    assert parse_indonesian_date_range("25 Des s/d 5 Jan", default_year=2026) == ("2026-12-25", "2027-01-05")


def test_extract_pack_size_from_name():
    assert extract_pack_size_from_name("Oreo Biscuit Vanilla 133g") == "133g"
    assert extract_pack_size_from_name("Roma Malkist Abon 250gr") == "250gr"
    assert extract_pack_size_from_name("Khong Guan Classic 1.6 kg") == "1.6 kg"
    assert extract_pack_size_from_name("Nissin Wafer 12 x 25g") == "12 x 25g"
    assert extract_pack_size_from_name("Tango Cokelat 176 g") == "176 g"
    assert extract_pack_size_from_name("Plain Product Without Pack Size") is None


def test_sanitize_price():
    assert sanitize_price("Rp 14.500") == 14500.0
    assert sanitize_price("14.500") == 14500.0
    assert sanitize_price("Rp 8.200") == 8200.0
    assert sanitize_price("8200") == 8200.0
    assert sanitize_price(8200) == 8200.0
    assert sanitize_price(10500.5) == 10500.5
    assert sanitize_price("invalid") is None
    assert sanitize_price(None) is None
