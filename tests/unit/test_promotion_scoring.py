from datetime import datetime, timezone

from app.services.ranking.scorer import PromotionScorer


def test_change_impact_weights_material_changes():
    price = PromotionScorer.calculate_change_impact([
        {"field": "promo_price", "event_type": "PRICE_OR_VALUE_CHANGED"},
    ])
    mechanic = PromotionScorer.calculate_change_impact([
        {"field": "promotion_type", "event_type": "MECHANIC_CHANGED"},
    ])
    assert price == 0.40
    assert mechanic == 0.35
    assert price > mechanic


def test_multiple_changes_are_bounded():
    changes = [
        {"field": "promo_price", "event_type": "PRICE_OR_VALUE_CHANGED"},
        {"field": "discount_percentage", "event_type": "PRICE_OR_VALUE_CHANGED"},
        {"field": "promotion_type", "event_type": "MECHANIC_CHANGED"},
        {"field": "end_date", "event_type": "DATES_CHANGED"},
        {"field": "channel", "event_type": "TERMS_CHANGED"},
    ]
    assert PromotionScorer.calculate_change_impact(changes) == 1.0


def test_material_change_can_lift_rank_score():
    now = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
    common = dict(
        promotion_type="DISCOUNT",
        discount_percentage=30,
        source_reliability=0.85,
        last_seen_at=now,
        category="BISCUIT",
        competitor_importance=0.5,
        ai_confidence=0.9,
        now=now,
    )
    unchanged = PromotionScorer.compute_total_score(**common)
    changed = PromotionScorer.compute_total_score(**common, change_impact=0.75)
    assert changed > unchanged


def test_invalid_change_impact_is_bounded():
    now = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
    score = PromotionScorer.compute_total_score(
        promotion_type="DISCOUNT",
        discount_percentage=30,
        source_reliability=0.85,
        last_seen_at=now,
        category="BISCUIT",
        competitor_importance=0.5,
        ai_confidence=0.9,
        change_impact=999,
        now=now,
    )
    assert 0.0 <= score <= 1.0
