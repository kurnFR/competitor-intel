"""Deterministic promotion identity generation.

The fingerprint is an identity aid, not proof that two observations are the
same promotion. Callers must still apply entity-resolution and ambiguity rules
before linking an observation to a canonical promotion.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
import re
from typing import Any


IDENTITY_VERSION = "v1"


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value).strip().casefold())
    return text or None


def _normalize_number(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    if isinstance(value, float):
        return format(Decimal(str(value)).normalize(), "f")
    return str(value).strip()


def _normalize_datetime(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return _normalize_text(value)


def _identity_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Build the stable, commercially meaningful identity payload.

    Volatile fields such as rank score, AI confidence, observation timestamps,
    descriptions and source reliability are intentionally excluded.
    """
    return {
        "identity_version": IDENTITY_VERSION,
        "competitor_id": str(data.get("competitor_id")) if data.get("competitor_id") else None,
        "brand_id": str(data.get("brand_id")) if data.get("brand_id") else None,
        "product_id": str(data.get("product_id")) if data.get("product_id") else None,
        "retailer_id": str(data.get("retailer_id")) if data.get("retailer_id") else None,
        "product_name": _normalize_text(data.get("product_name")),
        "sku": _normalize_text(data.get("sku")),
        "pack_size": _normalize_text(data.get("pack_size")),
        "promotion_type": _normalize_text(data.get("promotion_type")),
        "buy_quantity": data.get("buy_quantity"),
        "free_quantity": data.get("free_quantity"),
        "bundle_quantity": data.get("bundle_quantity"),
        "cashback_amount": _normalize_number(data.get("cashback_amount")),
        "voucher_amount": _normalize_number(data.get("voucher_amount")),
        "minimum_purchase_amount": _normalize_number(data.get("minimum_purchase_amount")),
        "minimum_purchase_quantity": data.get("minimum_purchase_quantity"),
        "gift_description": _normalize_text(data.get("gift_description")),
        "promo_price": _normalize_number(data.get("promo_price")),
        "currency": _normalize_text(data.get("currency")),
        "promotion_title": _normalize_text(data.get("promotion_title")),
        "start_date": _normalize_datetime(data.get("start_date")),
        "end_date": _normalize_datetime(data.get("end_date")),
        "channel": _normalize_text(data.get("channel")),
        "geography": _normalize_text(data.get("geography")),
    }


def promotion_identity_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Return the canonical payload used by the fingerprint and for testing."""
    return _identity_payload(data)


def promotion_identity_fingerprint(data: dict[str, Any]) -> str:
    """Return a deterministic SHA-256 fingerprint for a promotion identity."""
    payload = _identity_payload(data)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
