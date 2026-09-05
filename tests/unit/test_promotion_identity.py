import unittest

from app.services.promotions.identity import (
    IDENTITY_VERSION,
    promotion_identity_fingerprint,
    promotion_identity_payload,
)


class PromotionIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base = {
            "retailer_id": "retailer-1",
            "brand_id": "brand-1",
            "product_id": "product-1",
            "product_name": "  Biscuit   Original  ",
            "sku": "SKU-001",
            "promotion_type": "DISCOUNT",
            "promo_price": 8000.0,
            "currency": "IDR",
            "start_date": "2026-09-01",
            "end_date": "2026-09-30",
            "channel": "STORE",
            "geography": "Indonesia",
        }

    def test_same_identity_is_stable(self) -> None:
        self.assertEqual(
            promotion_identity_fingerprint(self.base),
            promotion_identity_fingerprint(dict(self.base)),
        )

    def test_whitespace_and_case_do_not_change_identity(self) -> None:
        changed = dict(self.base)
        changed["product_name"] = "biscuit original"
        changed["promotion_type"] = "discount"
        changed["currency"] = "idr"
        self.assertEqual(
            promotion_identity_fingerprint(self.base),
            promotion_identity_fingerprint(changed),
        )

    def test_material_promotion_change_changes_identity(self) -> None:
        changed = dict(self.base)
        changed["promotion_type"] = "BUY_GET"
        changed["buy_quantity"] = 2
        changed["free_quantity"] = 1
        self.assertNotEqual(
            promotion_identity_fingerprint(self.base),
            promotion_identity_fingerprint(changed),
        )

    def test_volatile_fields_do_not_change_identity(self) -> None:
        changed = dict(self.base)
        changed["ai_confidence"] = 0.12
        changed["rank_score"] = 99.0
        changed["source_reliability"] = 0.2
        changed["observed_at"] = "2026-09-05T10:00:00+07:00"
        self.assertEqual(
            promotion_identity_fingerprint(self.base),
            promotion_identity_fingerprint(changed),
        )

    def test_payload_contains_identity_version(self) -> None:
        payload = promotion_identity_payload(self.base)
        self.assertEqual(IDENTITY_VERSION, payload["identity_version"])
        self.assertNotIn("rank_score", payload)
        self.assertNotIn("ai_confidence", payload)


if __name__ == "__main__":
    unittest.main()
