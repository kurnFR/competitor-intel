"""Sales-channel normalisation shared by the pipeline and the API."""
from __future__ import annotations

from typing import Optional

VERIFIED_CHANNELS = {"Retail", "Modern Trade", "E-commerce", "General Trade", "Wholesale", "Distributor", "Foodservice"}

# Retailer.channel_type / raw labels -> reporting channel.
_ALIASES = {
    "minimarket": "Modern Trade",
    "supermarket": "Modern Trade",
    "hypermarket": "Modern Trade",
    "modern trade": "Modern Trade",
    "modern_trade": "Modern Trade",
    "ecommerce": "E-commerce",
    "e-commerce": "E-commerce",
    "marketplace": "E-commerce",
    "general trade": "General Trade",
    "general_trade": "General Trade",
    "wholesale": "Wholesale",
    "foodservice": "Foodservice",
}


def normalize_channel(value: Optional[str]) -> Optional[str]:
    """Return a reporting channel, or None when the value is unknown."""
    if not value:
        return None
    key = str(value).strip().lower()
    for verified in VERIFIED_CHANNELS:
        if key == verified.lower():
            return verified
    return _ALIASES.get(key)


def display_channel(promotion_channel: Optional[str], retailer_channel_type: Optional[str]) -> str:
    """Channel to show: the promotion's own value, else derived from its retailer."""
    return normalize_channel(promotion_channel) or normalize_channel(retailer_channel_type) or "N/A"


def retailer_types_for(channel: str) -> list[str]:
    """Upper-cased Retailer.channel_type values that map to a reporting channel."""
    return sorted({alias.upper() for alias, target in _ALIASES.items() if target == channel})
