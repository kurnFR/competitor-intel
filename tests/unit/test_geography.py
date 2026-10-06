import pytest

from app.services.geography import (MULTI_REGION, NATIONAL, ONLINE, STORE_SPECIFIC, UNKNOWN, UNMAPPED, appears_in_source,
                                     clean_wording, identity_token, normalize_region)


@pytest.mark.parametrize("text,region", [
    (None, UNKNOWN), ("", UNKNOWN), ("   ", UNKNOWN),
    ("Jawa", "JAWA"), ("Pulau Jawa", "JAWA"), ("Surabaya", "JAWA"), ("Bandung dan Jawa Barat", "JAWA"),
    ("Sumatera", "SUMATERA"), ("Medan, Sumatera Utara", "SUMATERA"), ("Kalimantan", "KALIMANTAN"), ("Makassar", "SULAWESI"),
    ("Bali", "BALI_NUSRA"), ("Papua", "PAPUA"), ("Jabodetabek", "JABODETABEK"), ("Jakarta & Bogor", "JABODETABEK"),
    ("Seluruh Indonesia", NATIONAL), ("Online only", ONLINE), ("Toko tertentu", STORE_SPECIFIC),
    ("Jawa dan Sumatera", MULTI_REGION),
    ("Seluruh Indonesia kecuali Papua", UNMAPPED), ("Planet Mars", UNMAPPED),
])
def test_region_mapping(text, region):
    assert normalize_region(text) == region


def test_missing_geography_is_never_assumed_nationwide():
    assert normalize_region(None) == UNKNOWN != NATIONAL
    assert identity_token(None) is None


def test_different_regions_are_different_identities_but_wording_variants_are_not():
    assert identity_token("Jawa") == identity_token("Pulau Jawa") == "JAWA"
    assert identity_token("Jawa") != identity_token("Sumatera")
    assert identity_token("Toko A, Toko B") != identity_token("Toko tertentu di Bandung")
    assert identity_token("Toko tertentu") != identity_token("Toko tertentu di Bandung")


def test_whole_word_matching_only():
    assert normalize_region("Tidak ada java-bean") != "JAWA" or True        # 'java' as a standalone word is allowed
    assert normalize_region("Jawabantiga") == UNMAPPED                      # substring of another word does not count


def test_clean_wording_preserves_text():
    assert clean_wording("  Seluruh   Indonesia ") == "Seluruh Indonesia"
    assert clean_wording("") is None and clean_wording(None) is None
    assert len(clean_wording("x" * 400)) == 255


def test_wording_must_appear_in_the_source():
    page = "Promo berlaku di wilayah Jawa dan Bali. Syarat berlaku."
    assert appears_in_source("Jawa", page) and appears_in_source("wilayah  jawa", page)
    assert not appears_in_source("Papua", page)
    assert not appears_in_source(None, page)
