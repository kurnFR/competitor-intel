"""Multi-source conflict arbitration (PRD 16): never silently overwrite one source with another."""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.source import SourceRegistry

APPLY = "APPLY"      # ordinary update: take the new values
KEEP = "KEEP"        # a clearly less authoritative source disagrees: keep current values, retain the observation
REVIEW = "REVIEW"    # genuinely unresolved: freeze current values, hide from the Top 10, ask a person

RECENT_DAYS = 7                 # facts verified within this window are "current"; older facts are simply superseded
AUTHORITY_MARGIN = 0.15         # reliability gap that decides between two sources
PRICE_TOLERANCE = 0.01          # 1 %
DISCOUNT_TOLERANCE = 1.0        # percentage points

_PRICE_FIELDS = {"promo_price", "regular_price"}
_EXACT_FIELDS = {"start_date", "end_date", "buy_quantity", "free_quantity", "promotion_type"}
LABELS = {
    "promo_price": "promo price", "regular_price": "regular price", "discount_percentage": "discount %",
    "start_date": "start date", "end_date": "end date", "buy_quantity": "buy quantity", "free_quantity": "free quantity",
    "promotion_type": "mechanic",
}


def _num(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(Decimal(str(value)))
    except Exception:
        return None


def is_material(change: Dict[str, Any]) -> bool:
    """A difference that would change what a marketer concludes (not rounding noise)."""
    field, old, new = change["field"], change.get("previous_value"), change.get("new_value")
    if field in _EXACT_FIELDS:
        return True
    a, b = _num(old), _num(new)
    if a is None or b is None:
        return False
    if field in _PRICE_FIELDS:
        return a == 0 or abs(a - b) / abs(a) > PRICE_TOLERANCE
    if field == "discount_percentage":
        return abs(a - b) >= DISCOUNT_TOLERANCE
    return False


def material_changes(changes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [c for c in changes if c["field"] in LABELS and is_material(c)]


def _fmt(field: str, value: Any) -> str:
    if value is None:
        return "-"
    if field in _PRICE_FIELDS:
        n = _num(value)
        return f"Rp{n:,.0f}" if n is not None else str(value)
    if field == "discount_percentage":
        n = _num(value)
        return f"{n:g}%" if n is not None else str(value)
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    return str(value)[:10] if field.endswith("_date") else str(value)


def arbitrate(db: Session, promotion: Any, changes: List[Dict[str, Any]], *, new_source_id, new_reliability: float,
              now: datetime) -> Tuple[str, List[Dict[str, Any]], str]:
    """Decide what to do with an observation that differs from the stored promotion.

    Returns (verdict, material_changes, explanation). Observations are always retained by the caller.
    Retailer, channel, geography and period are part of promotion identity, so by the time we get here the two
    observations already describe the same commercial activity.
    """
    material = material_changes(changes)
    if not material:
        return APPLY, [], "no material difference"
    if promotion.source_id is None or new_source_id is None or promotion.source_id == new_source_id:
        return APPLY, material, "same source: a normal change over time"
    if promotion.last_verified_at is None or now - promotion.last_verified_at > timedelta(days=RECENT_DAYS):
        return APPLY, material, f"existing facts were last verified more than {RECENT_DAYS} days ago; the newer observation supersedes them"

    current = db.get(SourceRegistry, promotion.source_id)
    current_reliability = float(current.reliability_score) if current is not None else 0.85
    gap = float(new_reliability) - current_reliability
    if gap >= AUTHORITY_MARGIN:
        return APPLY, material, "the new source is clearly more authoritative"
    if gap <= -AUTHORITY_MARGIN:
        return KEEP, material, "a clearly less authoritative source disagrees; current values kept"
    return REVIEW, material, "two comparable sources disagree and neither is clearly newer or more authoritative"


def describe(material: List[Dict[str, Any]], *, current_source: str, new_source: str, reason: str) -> str:
    lines = [f"Two sources disagree: {reason}.", f"Current ({current_source})  vs  new ({new_source}):"]
    for c in material:
        lines.append(f"- {LABELS[c['field']]}: {_fmt(c['field'], c.get('previous_value'))} vs {_fmt(c['field'], c.get('new_value'))}")
    return "\n".join(lines)
