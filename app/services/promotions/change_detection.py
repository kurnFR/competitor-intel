"""Detect material changes between canonical promotion state and a new observation.

Changes are reported separately from canonical persistence so marketing can see
real commercial changes without silently treating every extraction difference
as a new promotion.
"""

from __future__ import annotations

from typing import Any


TRACKED_FIELDS = (
    "regular_price",
    "promo_price",
    "discount_percentage",
    "promotion_type",
    "buy_quantity",
    "free_quantity",
    "bundle_quantity",
    "cashback_amount",
    "voucher_amount",
    "minimum_purchase_amount",
    "minimum_purchase_quantity",
    "gift_description",
    "channel",
    "geography",
    "start_date",
    "end_date",
)


def detect_promotion_changes(promotion: Any, item: Any) -> list[dict[str, Any]]:
    """Return material field changes before canonical values are refreshed."""
    changes: list[dict[str, Any]] = []
    for field in TRACKED_FIELDS:
        if not hasattr(item, field) or not hasattr(promotion, field):
            continue
        new_value = getattr(item, field)
        old_value = getattr(promotion, field)
        if new_value is None or new_value == old_value:
            continue
        changes.append({
            "field": field,
            "previous_value": old_value,
            "new_value": new_value,
        })
    return changes
