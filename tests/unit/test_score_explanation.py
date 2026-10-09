from datetime import datetime, timedelta, timezone

import pytest

from app.services.ranking.scorer import UNDATED_PENALTY, PromotionScorer

NOW = datetime(2026, 10, 6, 12, tzinfo=timezone.utc)


def kw(**over):
    base = dict(promotion_type="DISCOUNT", discount_percentage=30, source_reliability=0.9, last_seen_at=NOW - timedelta(days=2),
                category="BISCUIT", competitor_importance=0.6, ai_confidence=0.85, change_impact=0.4, dates_known=True, now=NOW)
    base.update(over)
    return base


@pytest.mark.parametrize("over", [
    {}, {"promotion_type": "BUY_X_GET_Y", "discount_percentage": 50}, {"dates_known": False}, {"category": "SOAP"},
    {"change_impact": 0.0}, {"last_seen_at": NOW - timedelta(days=120)}, {"source_reliability": None}, {"discount_percentage": None},
])
def test_explanation_always_matches_the_real_score(over):
    explained = PromotionScorer.explain(**kw(**over))
    assert explained["score"] == PromotionScorer.compute_total_score(**kw(**over))


def test_components_add_up_to_the_score():
    e = PromotionScorer.explain(**kw())
    assert [c["key"] for c in e["components"]] == ["strength", "reliability", "freshness", "relevance", "importance", "confidence", "change"]
    assert abs(sum(c["weight"] for c in e["components"]) - 1.0) < 1e-9
    assert abs(sum(c["points"] for c in e["components"]) - e["base"]) < 1e-3
    assert e["score"] == pytest.approx(e["base"], abs=1e-4) and e["undated_penalty"] is None
    assert all(0.0 <= c["value"] <= 1.0 for c in e["components"])


def test_undated_penalty_is_shown_and_applied():
    e = PromotionScorer.explain(**kw(dates_known=False))
    assert e["undated_penalty"] == UNDATED_PENALTY
    assert e["score"] == pytest.approx(e["base"] * UNDATED_PENALTY, abs=1e-4)


def test_weights_are_the_documented_ones():
    assert {k: w for k, _, w in PromotionScorer.COMPONENTS} == {
        "strength": 0.25, "reliability": 0.15, "freshness": 0.10, "relevance": 0.15, "importance": 0.10, "confidence": 0.10, "change": 0.15}
