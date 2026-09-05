from types import SimpleNamespace

from app.services.validation.lifecycle import evaluate_lifecycle
from app.services.validation.validator import PromotionValidator


def item(**overrides):
    values = {
        "product_name": "Roma Kelapa 300g",
        "brand": "Roma",
        "competitor": "Mayora",
        "category": "BISCUIT",
        "regular_price": 12000.0,
        "promo_price": 9000.0,
        "discount_percentage": None,
        "promotion_type": "DISCOUNT",
        "buy_quantity": None,
        "free_quantity": None,
        "start_date": "2026-09-01",
        "end_date": "2026-09-30",
        "confidence": 0.9,
        "evidence_quote": "Roma Kelapa 300g Rp9.000",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_validator_derives_discount_from_regular_and_promo_price():
    valid, reason, start_dt, end_dt, discount = PromotionValidator.validate_and_normalize(item())

    assert valid is True
    assert reason == "Valid"
    assert start_dt is not None
    assert end_dt is not None
    assert discount == 25.0


def test_validator_rejects_invalid_date():
    valid, reason, *_ = PromotionValidator.validate_and_normalize(
        item(start_date="2026-99-01")
    )

    assert valid is False
    assert "Invalid date format" in reason


def test_validator_rejects_end_before_start():
    valid, reason, *_ = PromotionValidator.validate_and_normalize(
        item(start_date="2026-09-30", end_date="2026-09-01")
    )

    assert valid is False
    assert reason == "Promotion end date is before start date"


def test_validator_allows_missing_dates_without_fabrication():
    valid, reason, start_dt, end_dt, _ = PromotionValidator.validate_and_normalize(
        item(start_date=None, end_date=None)
    )

    assert valid is True
    assert reason == "Valid"
    assert start_dt is None
    assert end_dt is None


def test_validator_rejects_promo_price_above_regular_price():
    valid, reason, *_ = PromotionValidator.validate_and_normalize(
        item(regular_price=9000.0, promo_price=12000.0)
    )

    assert valid is False
    assert "exceeds regular price" in reason


def test_validator_calculates_buy_x_get_y_effective_discount():
    valid, reason, _, _, discount = PromotionValidator.validate_and_normalize(
        item(
            promotion_type="BUY_X_GET_Y",
            regular_price=None,
            promo_price=None,
            discount_percentage=0.0,
            buy_quantity=2,
            free_quantity=1,
        )
    )

    assert valid is True
    assert reason == "Valid"
    assert discount == 33.33


def test_lifecycle_missing_dates_is_unknown():
    assert evaluate_lifecycle(None, None) == "UNKNOWN"


def test_lifecycle_classifies_upcoming_active_and_expired():
    from datetime import datetime, timezone

    now = datetime(2026, 9, 5, tzinfo=timezone.utc)

    assert evaluate_lifecycle(
        datetime(2026, 9, 6, tzinfo=timezone.utc),
        datetime(2026, 9, 10, tzinfo=timezone.utc),
        now=now,
    ) == "UPCOMING"
    assert evaluate_lifecycle(
        datetime(2026, 9, 1, tzinfo=timezone.utc),
        datetime(2026, 9, 10, tzinfo=timezone.utc),
        now=now,
    ) == "ACTIVE"
    assert evaluate_lifecycle(
        datetime(2026, 8, 1, tzinfo=timezone.utc),
        datetime(2026, 8, 31, tzinfo=timezone.utc),
        now=now,
    ) == "EXPIRED"
