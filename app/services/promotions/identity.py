"""Deterministic promotion identity generation.

Fingerprints are identity aids, not proof that two observations are the same
promotion. Callers must still apply entity-resolution and ambiguity rules.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
import re
from typing import Any


IDENTITY_VERSION = "v1"
SOURCE_IDENTITY_VERSION = "v2"


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


def _hash_payload(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _identity_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Build the legacy canonical identity payload.

    Kept unchanged for backward compatibility with existing v1 fingerprints.
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


def _source_identity_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Build a stable commercial identity independent of mutable entity IDs.

    Entity resolution can improve after the first crawl, and marketing copy
    can change while the same offer remains active. Therefore this identity
    deliberately excludes canonical UUIDs, promotion title, and dates. The
    retailer/channel/geography boundary remains part of identity so identical
    offers at different retailers are not silently merged.
    """
    return {
        "identity_version": SOURCE_IDENTITY_VERSION,
        "retailer": _normalize_text(data.get("retailer")),
        "brand": _normalize_text(data.get("brand")),
        "competitor": _normalize_text(data.get("competitor")),
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
        "channel": _normalize_text(data.get("channel")),
        "geography": _normalize_text(data.get("geography")),
    }


def promotion_identity_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Return the legacy payload used by the v1 fingerprint."""
    return _identity_payload(data)


def promotion_identity_fingerprint(data: dict[str, Any]) -> str:
    """Return the deterministic legacy v1 SHA-256 fingerprint."""
    return _hash_payload(_identity_payload(data))


def promotion_source_identity_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Return the v2 commercial identity payload used for stable matching."""
    return _source_identity_payload(data)


def promotion_source_identity_fingerprint(data: dict[str, Any]) -> str:
    """Return a stable SHA-256 identity independent of canonical entity IDs."""
    return _hash_payload(_source_identity_payload(data))
