from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.services.promotions.conflicts import APPLY, KEEP, REVIEW, arbitrate, describe, is_material, material_changes

NOW = datetime(2026, 10, 3, 12, tzinfo=timezone.utc)


def change(field, old, new):
    return {"field": field, "previous_value": old, "new_value": new}


@pytest.mark.parametrize("field,old,new,expected", [
    ("promo_price", 7000, 7050, False), ("promo_price", 7000, 7071, True), ("promo_price", 7000, 6500, True),
    ("regular_price", 10000, 10000.5, False), ("promo_price", 0, 100, True),
    ("discount_percentage", 30, 30.5, False), ("discount_percentage", 30, 35, True),
    ("end_date", "2026-10-15", "2026-10-20", True), ("promotion_type", "DISCOUNT", "BUY_X_GET_Y", True),
    ("channel", "Modern Trade", "E-commerce", False), ("promo_price", None, 5000, False),
])
def test_what_counts_as_material(field, old, new, expected):
    assert is_material(change(field, old, new)) is expected


class FakeDb:
    def __init__(self, reliability=0.85):
        self.reliability = reliability

    def get(self, model, key):
        return SimpleNamespace(reliability_score=self.reliability, name="Current source")


def promo(**kw):
    base = dict(source_id="A", last_verified_at=NOW - timedelta(days=1))
    base.update(kw)
    return SimpleNamespace(**base)


PRICE = [change("promo_price", 7000, 6500)]


def decide(promotion, changes=PRICE, *, new_source="B", reliability=0.85, current_reliability=0.85):
    return arbitrate(FakeDb(current_reliability), promotion, changes, new_source_id=new_source, new_reliability=reliability, now=NOW)[0]


def test_no_material_difference_is_an_ordinary_update():
    assert decide(promo(), [change("promo_price", 7000, 7010)]) == APPLY
    assert decide(promo(), []) == APPLY


def test_same_source_or_unknown_source_is_a_normal_change_over_time():
    assert decide(promo(), new_source="A") == APPLY
    assert decide(promo(source_id=None)) == APPLY
    assert decide(promo(), new_source=None) == APPLY


def test_older_facts_are_simply_superseded_by_a_newer_observation():
    assert decide(promo(last_verified_at=NOW - timedelta(days=10))) == APPLY
    assert decide(promo(last_verified_at=None)) == APPLY


def test_clear_authority_difference_decides_it():
    assert decide(promo(), reliability=0.95, current_reliability=0.75) == APPLY      # new is clearly more authoritative
    assert decide(promo(), reliability=0.70, current_reliability=0.90) == KEEP       # new is clearly less authoritative


def test_comparable_recent_sources_that_disagree_go_to_a_person():
    assert decide(promo()) == REVIEW
    assert decide(promo(), reliability=0.90, current_reliability=0.80) == REVIEW     # gap below the margin


def test_only_material_fields_are_reported_and_explained():
    verdict, material, why = arbitrate(FakeDb(), promo(), [change("promo_price", 7000, 6500), change("channel", "a", "b")],
                                       new_source_id="B", new_reliability=0.85, now=NOW)
    assert [c["field"] for c in material] == ["promo_price"]
    text = describe(material, current_source="Indomaret", new_source="Hemat.id", reason=why)
    assert "Rp7,000 vs Rp6,500" in text and "Indomaret" in text and "Hemat.id" in text
