"""Detect material promotion changes for marketing intelligence."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
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


def _comparable(value: Any, field: str) -> Any:
    """Normalize source/canonical representations before change detection."""
    if value is None:
        return None
    if field in _DATE_FIELDS:
        if isinstance(value, datetime):
            return value.astimezone(value.tzinfo).date().isoformat() if value.tzinfo else value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        text = str(value).strip()
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            return text
    if field in _PRICE_FIELDS and isinstance(value, (Decimal, float, int)):
        return Decimal(str(value))
    return value


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
        if new_value is None or _comparable(new_value, field) == _comparable(old_value, field):
            continue
        changes.append({
            "event_type": _event_type(field),
            "field": field,
            "previous_value": old_value,
            "new_value": new_value,
        })
    return changes
