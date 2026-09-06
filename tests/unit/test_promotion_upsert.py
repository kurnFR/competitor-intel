from datetime import datetime, timezone
from uuid import uuid4

from app.models.promotion import Promotion, PromotionEvidence, PromotionObservation
from app.schemas.ai import ExtractedPromotionItem
from app.services.promotions.upsert import upsert_promotion_observation


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def all(self):
        return list(self.rows)

    def one_or_none(self):
        if not self.rows:
            return None
        if len(self.rows) > 1:
            raise AssertionError("FakeQuery expected at most one matching row")
        return self.rows[0]


class FakeSession:
    """Small deterministic session double for the service-level upsert tests."""

    def __init__(self):
        self.rows = {Promotion: [], PromotionObservation: [], PromotionEvidence: []}

    def query(self, model):
        return FakeQuery(self.rows[model])

    def add(self, obj):
        self.rows[type(obj)].append(obj)

    def flush(self):
        for model_rows in self.rows.values():
            for obj in model_rows:
                if getattr(obj, "id", None) is None:
                    obj.id = uuid4()


def _item(**overrides):
    values = {
        "product_name": "Roma Kelapa 300g", "brand": "Roma", "competitor": "Mayora",
        "category": "BISCUIT", "pack_size": "300g", "regular_price": 10000,
        "promo_price": 7000, "discount_percentage": 30, "promotion_type": "DISCOUNT",
        "start_date": "2026-09-01", "end_date": "2026-09-30", "retailer": "Indomaret",
        "evidence_quote": "Roma Kelapa 300g Rp7.000 diskon 30%", "confidence": 0.95,
    }
    values.update(overrides)
    return ExtractedPromotionItem(**values)


def test_upsert_is_idempotent_for_same_document_and_promotion():
    db = FakeSession()
    document_id = uuid4()
    observed_at = datetime(2026, 9, 5, 14, 0, tzinfo=timezone.utc)
    metadata = {
        "model": "test-model", "status": "SUCCESS", "extracted_at": observed_at,
        "raw_response_hash": "a" * 64, "rejected_count": 0,
    }

    first_promotion, first_observation, first_created = upsert_promotion_observation(
        db, document_id=document_id, item=_item(),
        raw_text="Roma Kelapa 300g Rp7.000 diskon 30%",
        extracted_json={"product_name": "Roma Kelapa 300g"}, observed_at=observed_at,
        source_url="https://example.test/promo", extraction_metadata=metadata,
    )
    second_metadata = {**metadata, "model": "test-model-v2", "raw_response_hash": "b" * 64}
    second_promotion, second_observation, second_created = upsert_promotion_observation(
        db, document_id=document_id, item=_item(),
        raw_text="Roma Kelapa 300g Rp7.000 diskon 30%",
        extracted_json={"product_name": "Roma Kelapa 300g", "revision": 2}, observed_at=observed_at,
        source_url="https://example.test/promo", extraction_metadata=second_metadata,
    )

    assert first_created is True
    assert second_created is False
    assert second_promotion is first_promotion
    assert second_observation is first_observation
    assert len(db.rows[Promotion]) == 1
    assert len(db.rows[PromotionObservation]) == 1
    assert len(db.rows[PromotionEvidence]) == 1
    assert second_observation.extraction_model == "test-model-v2"
    assert second_observation.extraction_raw_response_hash == "b" * 64
    assert second_observation.extracted_json["revision"] == 2


def test_missing_dates_do_not_erase_known_canonical_dates():
    db = FakeSession()
    observed_at = datetime(2026, 9, 10, 10, 0, tzinfo=timezone.utc)
    promotion, _, created = upsert_promotion_observation(
        db, document_id=uuid4(), item=_item(),
        raw_text="Roma Kelapa 300g Rp7.000 diskon 30%", observed_at=observed_at,
    )
    assert created is True
    original_start, original_end = promotion.start_date, promotion.end_date

    updated, _, second_created = upsert_promotion_observation(
        db, document_id=uuid4(), item=_item(start_date=None, end_date=None),
        raw_text="Roma Kelapa 300g Rp7.000 diskon 30%", observed_at=observed_at,
    )
    assert second_created is False
    assert updated is promotion
    assert updated.start_date == original_start
    assert updated.end_date == original_end


def test_missing_discount_does_not_erase_known_canonical_discount():
    db = FakeSession()
    observed_at = datetime(2026, 9, 10, 10, 0, tzinfo=timezone.utc)
    promotion, _, _ = upsert_promotion_observation(
        db, document_id=uuid4(), item=_item(),
        raw_text="Roma Kelapa 300g Rp7.000 diskon 30%", observed_at=observed_at,
    )

    updated, _, created = upsert_promotion_observation(
        db, document_id=uuid4(), item=_item(regular_price=None, discount_percentage=None),
        raw_text="Roma Kelapa 300g promo Rp7.000", observed_at=observed_at,
    )
    assert created is False
    assert updated is promotion
    assert updated.discount_percentage == 30


def test_explicit_later_date_can_correct_canonical_date():
    db = FakeSession()
    observed_at = datetime(2026, 9, 10, 10, 0, tzinfo=timezone.utc)
    promotion, _, _ = upsert_promotion_observation(
        db, document_id=uuid4(), item=_item(),
        raw_text="Roma Kelapa 300g Rp7.000 diskon 30%", observed_at=observed_at,
    )
    corrected, _, created = upsert_promotion_observation(
        db, document_id=uuid4(), item=_item(start_date="2026-09-02", end_date="2026-09-30"),
        raw_text="Roma Kelapa 300g Rp7.000 diskon 30%", observed_at=observed_at,
    )
    assert created is False
    assert corrected is promotion
    assert corrected.start_date.day == 2
    assert corrected.end_date.day == 30


def test_material_change_increases_rank_score_when_identity_is_stable():
    db = FakeSession()
    observed_at = datetime(2026, 9, 10, 10, 0, tzinfo=timezone.utc)
    promotion, _, _ = upsert_promotion_observation(
        db, document_id=uuid4(), item=_item(),
        raw_text="Roma Kelapa 300g Rp7.000 diskon 30%", observed_at=observed_at,
    )
    original_score = promotion.rank_score

    # Date correction is part of the stable source identity, so this is an
    # existing promotion and the change detector can boost its ranking.
    updated, _, created = upsert_promotion_observation(
        db, document_id=uuid4(), item=_item(start_date="2026-09-02"),
        raw_text="Roma Kelapa 300g Rp7.000 diskon 30% berlaku 2-30 September", observed_at=observed_at,
    )
    assert created is False
    assert updated is promotion
    assert updated.rank_score > original_score


if __name__ == "__main__":
    import unittest
    unittest.main()
