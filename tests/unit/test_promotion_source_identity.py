import unittest

from app.services.promotions.identity import (
    SOURCE_IDENTITY_VERSION,
    promotion_source_identity_fingerprint,
    promotion_source_identity_payload,
    source_identity_periods_compatible,
)


class PromotionSourceIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = {
            "retailer": "Indomaret",
            "brand": "Roma",
            "competitor": "Mayora",
            "product_name": "Roma Kelapa 300g",
            "sku": "SKU-001",
            "pack_size": "300g",
            "promotion_type": "DISCOUNT",
            "promo_price": 8000,
            "currency": "IDR",
            "channel": "STORE",
            "geography": "Indonesia",
            "promotion_title": "September Hemat",
            "start_date": "2026-09-01",
            "end_date": "2026-09-30",
            "retailer_id": "old-id",
            "brand_id": "old-brand-id",
        }

    def test_canonical_id_and_copy_date_changes_do_not_fragment(self) -> None:
        changed = dict(self.source)
        changed.update({
            "retailer_id": "new-id",
            "brand_id": "new-brand-id",
            "promotion_title": "Promo September Pilihan",
            "start_date": "2026-09-02",
            "end_date": "2026-09-29",
        })
        self.assertEqual(
            promotion_source_identity_fingerprint(self.source),
            promotion_source_identity_fingerprint(changed),
        )
        self.assertTrue(source_identity_periods_compatible(self.source, changed))

    def test_non_overlapping_recurring_campaigns_are_not_compatible(self) -> None:
        recurring = dict(self.source)
        recurring.update({
            "promotion_title": "Oktober Hemat",
            "start_date": "2026-10-01",
            "end_date": "2026-10-31",
        })
        self.assertEqual(
            promotion_source_identity_fingerprint(self.source),
            promotion_source_identity_fingerprint(recurring),
        )
        self.assertFalse(source_identity_periods_compatible(self.source, recurring))

    def test_adjacent_campaigns_without_overlap_are_not_compatible(self) -> None:
        next_campaign = dict(self.source)
        next_campaign.update({"start_date": "2026-10-01", "end_date": "2026-10-15"})
        self.assertFalse(source_identity_periods_compatible(self.source, next_campaign))

    def test_missing_dates_remain_compatible_as_uncertain(self) -> None:
        unknown = dict(self.source)
        unknown["start_date"] = None
        unknown["end_date"] = None
        self.assertTrue(source_identity_periods_compatible(self.source, unknown))

    def test_retailer_boundary_is_preserved(self) -> None:
        changed = dict(self.source)
        changed["retailer"] = "Alfamart"
        self.assertNotEqual(
            promotion_source_identity_fingerprint(self.source),
            promotion_source_identity_fingerprint(changed),
        )

    def test_material_mechanic_change_changes_identity(self) -> None:
        changed = dict(self.source)
        changed["promo_price"] = 7000
        self.assertNotEqual(
            promotion_source_identity_fingerprint(self.source),
            promotion_source_identity_fingerprint(changed),
        )

    def test_payload_excludes_mutable_identity_inputs(self) -> None:
        payload = promotion_source_identity_payload(self.source)
        self.assertEqual(SOURCE_IDENTITY_VERSION, payload["identity_version"])
        self.assertNotIn("promotion_title", payload)
        self.assertNotIn("start_date", payload)
        self.assertNotIn("end_date", payload)
        self.assertNotIn("retailer_id", payload)
        self.assertNotIn("brand_id", payload)


if __name__ == "__main__":
    unittest.main()
