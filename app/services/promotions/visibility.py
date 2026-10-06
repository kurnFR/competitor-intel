"""Which promotions count as "live" and eligible for the dashboard, Top 10, exports and statistics (PRD 13-14)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, exists, func, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.promotion import Promotion, PromotionEvidence
from app.models.source import SourceRegistry


@dataclass(frozen=True)
class Gate:
    key: str
    label: str          # what is wrong when a promotion fails this gate
    fix: str            # what to do about it
    condition: Any      # SQL condition that is TRUE when the promotion passes


def eligibility_gates(now: datetime, *, recency_days: int) -> List[Gate]:
    """The ordered rules a promotion must pass to be shown. One definition, used for filtering AND for explaining."""
    dated_active = and_(
        Promotion.status == "ACTIVE",
        or_(Promotion.end_date.is_(None), Promotion.end_date >= now),
    )
    undated = and_(Promotion.status == "UNKNOWN", Promotion.start_date.is_(None), Promotion.end_date.is_(None))
    gates = [
        Gate("active", "Not currently active (expired, not yet started, or no longer listed by its source)",
             "Nothing to fix: it is over, or its source stopped listing it. It returns automatically if it is seen again.",
             or_(dated_active, undated)),
        Gate("verified", f"Not verified within the last {recency_days} days",
             "Check that its source is being scanned successfully (Admin page).",
             Promotion.last_verified_at >= now - timedelta(days=recency_days)),
        Gate("evidence", "No stored evidence text",
             "Re-run a scan; promotions are only shown with a verbatim quote from the page.",
             exists().where(PromotionEvidence.promotion_id == Promotion.id,
                            func.length(func.trim(PromotionEvidence.evidence_text)) > 0)),
        Gate("source", "Its source is not an approved, active website",
             "Approve or resume the website on the Admin page.",
             exists().where(SourceRegistry.id == Promotion.source_id, SourceRegistry.is_active.is_(True),
                            SourceRegistry.approval_status == "APPROVED")),
        Gate("conflict", "Two sources disagree about it and nobody has decided yet",
             "Open the Review page and choose 'Use new values' or 'Keep current'.",
             Promotion.has_open_conflict.is_(False)),
    ]
    if settings.TOP10_REQUIRE_RESOLVED_IDENTITY:
        gates.append(Gate("identity", "No competitor or brand could be matched",
                          "Open the Review page to confirm the match, or add the competitor/brand.",
                          or_(Promotion.competitor_id.isnot(None), Promotion.brand_id.isnot(None))))
    if settings.TOP10_REQUIRE_KNOWN_GEOGRAPHY:
        gates.append(Gate("geography", "The page does not say where the promotion is valid",
                          "Set TOP10_REQUIRE_KNOWN_GEOGRAPHY=false to show these as 'Not stated'.",
                          Promotion.geography_region.notin_(["UNKNOWN", "UNMAPPED"])))
    return gates


def live_promotion_filter(now: datetime, *, recency_days: int):
    """SQL condition for promotions eligible to be shown to marketing: every gate must pass."""
    return and_(*[g.condition for g in eligibility_gates(now, recency_days=recency_days)])


def why_hidden(db: Session, promotion_id, *, now: Optional[datetime] = None, recency_days: int = 90) -> List[Dict[str, str]]:
    """The gates a single promotion fails (empty list = it is shown)."""
    now = now or datetime.now().astimezone()
    failed = []
    for gate in eligibility_gates(now, recency_days=recency_days):
        passes = db.query(Promotion.id).filter(Promotion.id == promotion_id, gate.condition).first() is not None
        if not passes:
            failed.append({"key": gate.key, "label": gate.label, "fix": gate.fix})
    return failed


def gate_failure_counts(db: Session, *, now: Optional[datetime] = None, recency_days: int = 90) -> Dict[str, Any]:
    """How many stored promotions are shown, and how many fail each gate (a promotion can fail several)."""
    now = now or datetime.now().astimezone()
    gates = eligibility_gates(now, recency_days=recency_days)
    total = db.query(Promotion).count()
    shown = db.query(Promotion).filter(and_(*[g.condition for g in gates])).count()
    failures = []
    for gate in gates:
        n = db.query(Promotion).filter(~gate.condition).count()
        failures.append({"key": gate.key, "label": gate.label, "fix": gate.fix, "count": n})
    failures.sort(key=lambda f: -f["count"])
    return {"total": total, "shown": shown, "hidden": total - shown, "gates": failures}
