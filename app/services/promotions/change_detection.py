"""Detect material promotion changes for marketing intelligence."""
from __future__ import annotations

from typing import Any

TRACKED_FIELDS = (
    "regular_price", "promo_price", "discount_percentage", "promotion_type",
    "buy_quantity", "free_quantity", "bundle_quantity", "cashback_amount",
    "voucher_amount", "minimum_purchase_amount", "minimum_purchase_quantity",
    "gift_description", "channel", "geography", "start_date", "end_date",
)

_PRICE_FIELDS = {"regular_price", "promo_price", "discount_percentage", "cashback_amount", "voucher_amount"}
_MECHANIC_FIELDS = {
    "promotion_type", "buy_quantity", "free_quantity", "bundle_quantity",
    "minimum_purchase_amount", "minimum_purchase_quantity", "gift_description",
}
_DATE_FIELDS = {"start_date", "end_date"}


def _event_type(field: str) -> str:
    if field in _PRICE_FIELDS:
        return "PRICE_OR_VALUE_CHANGED"
    if field in _MECHANIC_FIELDS:
        return "MECHANIC_CHANGED"
    if field in _DATE_FIELDS:
        return "DATES_CHANGED"
    return "TERMS_CHANGED"


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
            "event_type": _event_type(field),
            "field": field,
            "previous_value": old_value,
            "new_value": new_value,
        })
    return changes
