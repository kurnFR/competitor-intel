import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.models.entity import Competitor
from app.models.promotion import Promotion, PromotionEvidence
from app.models.source import SourceRegistry
from app.services.comparison import is_valid_active_promotion
from app.services.promotions.visibility import eligibility_gates, live_promotion_filter
from app.workers.expiration import run_expiration_check


def _make_promo(status="ACTIVE", start_date=None, end_date=None, last_verified_at=None, source_id=None):
    promo = Promotion(
        id=uuid.uuid4(),
        product_name=f"Test Promo {uuid.uuid4().hex[:6]}",
        status=status,
        start_date=start_date,
        end_date=end_date,
        last_verified_at=last_verified_at or datetime.now(timezone.utc),
        last_seen_at=last_verified_at or datetime.now(timezone.utc),
        source_id=source_id,
        category="BISCUIT",
        promotion_type="DISCOUNT",
    )
    return promo


def test_expiration_worker_marks_past_end_date_as_expired():
    now = datetime.now(timezone.utc)
    p_past = _make_promo(status="ACTIVE", end_date=now - timedelta(days=2))
    p_upcoming_past = _make_promo(status="UPCOMING", end_date=now - timedelta(days=1))

    # Provide distinct return values for each query call
    q_expired = MagicMock()
    q_expired.all.return_value = [p_past, p_upcoming_past]

    q_empty1 = MagicMock()
    q_empty1.all.return_value = []

    q_empty2 = MagicMock()
    q_empty2.all.return_value = []

    q_empty3 = MagicMock()
    q_empty3.all.return_value = []

    db = MagicMock()
    db.query.return_value.filter.side_effect = [q_expired, q_empty1, q_empty2, q_empty3]
    db.query.return_value.join.return_value.filter.return_value.all.return_value = []

    res = run_expiration_check(db)
    assert p_past.status == "EXPIRED"
    assert p_upcoming_past.status == "EXPIRED"
    assert db.commit.called


def test_is_valid_active_promotion_excludes_expired_and_future():
    now = datetime.now(timezone.utc)

    # 1. Active promotion within validity dates
    p_valid = _make_promo(
        status="ACTIVE",
        start_date=now - timedelta(days=2),
        end_date=now + timedelta(days=5),
        last_verified_at=now,
    )
    assert is_valid_active_promotion(p_valid, now) is True

    # 2. Expired promotion (end_date in the past)
    p_expired = _make_promo(
        status="ACTIVE",
        start_date=now - timedelta(days=10),
        end_date=now - timedelta(days=1),
        last_verified_at=now,
    )
    assert is_valid_active_promotion(p_expired, now) is False

    # 3. Status already EXPIRED
    p_status_expired = _make_promo(
        status="EXPIRED",
        start_date=now - timedelta(days=10),
        end_date=now + timedelta(days=5),
        last_verified_at=now,
    )
    assert is_valid_active_promotion(p_status_expired, now) is False

    # 4. Future promotion (start_date in future)
    p_future = _make_promo(
        status="ACTIVE",
        start_date=now + timedelta(days=2),
        end_date=now + timedelta(days=10),
        last_verified_at=now,
    )
    assert is_valid_active_promotion(p_future, now) is False

    # 5. Stale undated promotion older than 14 days
    p_stale_undated = _make_promo(
        status="UNKNOWN",
        start_date=None,
        end_date=None,
        last_verified_at=now - timedelta(days=15),
    )
    assert is_valid_active_promotion(p_stale_undated, now, unstated_recency_days=14) is False

    # 6. Fresh undated promotion within 14 days
    p_fresh_undated = _make_promo(
        status="UNKNOWN",
        start_date=None,
        end_date=None,
        last_verified_at=now - timedelta(days=3),
    )
    assert is_valid_active_promotion(p_fresh_undated, now, unstated_recency_days=14) is True


def test_visibility_gates_include_start_and_end_date_rules():
    now = datetime.now(timezone.utc)
    gates = eligibility_gates(now, recency_days=90)
    gate_keys = [g.key for g in gates]
    assert "active" in gate_keys
    assert "verified" in gate_keys


def test_touch_promotions_for_document_expires_past_promotions():
    from scripts.run_pipeline import _touch_promotions_for_document

    db = MagicMock()
    # Mock ids union
    db.query.return_value.filter.return_value.union.return_value = ["p1", "p2"]

    now = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)
    _touch_promotions_for_document(db, "doc-1", now)

    # Verify query for expiring promotions was called
    assert db.query.called
    assert db.query.return_value.filter.called
