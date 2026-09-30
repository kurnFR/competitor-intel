import json
from pathlib import Path

from app.services.extraction.evaluation import EvalReport, names_match, score_extraction

GOLD = Path(__file__).resolve().parent.parent / "fixtures" / "extraction_gold"


def test_names_match_ignores_order_and_extra_words():
    assert names_match("Roma Kelapa 300g", "Biskuit Roma Kelapa 300g")
    assert names_match("Kelapa Roma", "roma kelapa")
    assert not names_match("Roma Kelapa", "Malkist Abon")
    assert not names_match("", "Roma")


def test_perfect_extraction():
    exp = [{"product_name": "Roma Kelapa 300g", "promo_price": 7000, "discount_percentage": 30}]
    r = score_extraction(exp, [{"product_name": "Biskuit Roma Kelapa 300g", "promo_price": 7000.0, "discount_percentage": 30}])
    assert (r.precision, r.recall, r.f1) == (1.0, 1.0, 1.0)
    assert r.field_accuracy() == {"promo_price": 1.0, "discount_percentage": 1.0}


def test_misses_extras_and_wrong_fields_are_reported():
    exp = [{"product_name": "Roma Kelapa 300g", "promo_price": 7000}, {"product_name": "Malkist Abon 250g", "promo_price": 9000}]
    act = [{"product_name": "Roma Kelapa 300g", "promo_price": 6500}, {"product_name": "Lifebuoy Sabun", "promo_price": 4000}]
    r = score_extraction(exp, act)
    assert r.matched == 1 and r.missed == ["Malkist Abon 250g"] and r.unexpected == ["Lifebuoy Sabun"]
    assert r.precision == 0.5 and r.recall == 0.5
    assert r.field_accuracy() == {"promo_price": 0.0}


def test_one_extracted_item_cannot_match_two_expected():
    exp = [{"product_name": "Roma Kelapa"}, {"product_name": "Roma Kelapa 300g"}]
    r = score_extraction(exp, [{"product_name": "Roma Kelapa 300g"}])
    assert r.matched == 1 and len(r.missed) == 1


def test_empty_inputs_do_not_divide_by_zero():
    r = score_extraction([], [])
    assert (r.precision, r.recall, r.f1) == (0.0, 0.0, 0.0)


def test_merge_accumulates():
    a = score_extraction([{"product_name": "A B", "promo_price": 1}], [{"product_name": "A B", "promo_price": 1}])
    b = score_extraction([{"product_name": "C D"}], [])
    a.merge(b)
    assert a.expected == 2 and a.matched == 1 and a.missed == ["C D"]


def test_sample_gold_files_are_valid():
    pairs = [p for p in GOLD.glob("*.txt") if p.with_suffix(".json").exists()]
    assert pairs
    for txt in pairs:
        expected = json.loads(txt.with_suffix(".json").read_text(encoding="utf-8"))
        assert isinstance(expected, list) and all("product_name" in e for e in expected)
        for e in expected:                       # every labelled product really appears in the page text
            assert e["product_name"].split()[1].lower() in txt.read_text(encoding="utf-8").lower()
