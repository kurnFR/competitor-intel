"""Persist immutable, idempotent promotion change events."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Any, Iterable, Optional

from sqlalchemy.orm import Session

from app.models.promotion_change import PromotionChangeEvent


def _jsonable(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def _fingerprint(*, promotion_id, observation_id, event_type: str, field_name: Optional[str], previous_value: Any, new_value: Any) -> str:
    payload = {
        "promotion_id": str(promotion_id),
        "observation_id": str(observation_id) if observation_id else None,
        "event_type": event_type,
        "field_name": field_name,
        "previous_value": _jsonable(previous_value),
        "new_value": _jsonable(new_value),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def persist_promotion_change_events(
    db: Session,
    *,
    promotion,
    observation=None,
    changes: Optional[Iterable[dict[str, Any]]] = None,
    observed_at: datetime,
    document_id=None,
    change_impact: float = 0.0,
    superseded_promotion=None,
    created: bool = False,
) -> list[PromotionChangeEvent]:
    """Persist lifecycle/change events; repeated document processing is idempotent."""
    events: list[PromotionChangeEvent] = []

    def add_event(
        *, event_type: str, field_name: Optional[str] = None, previous_value: Any = None,
        new_value: Any = None, event_promotion=None, previous_promotion=None, impact: float = 0.0,
    ) -> None:
        target = event_promotion or promotion
        fingerprint = _fingerprint(
            promotion_id=target.id,
            observation_id=observation.id if observation else None,
            event_type=event_type,
            field_name=field_name,
            previous_value=previous_value,
            new_value=new_value,
        )
        existing = db.query(PromotionChangeEvent).filter(
            PromotionChangeEvent.event_fingerprint == fingerprint
        ).one_or_none()
        if existing is not None:
            events.append(existing)
            return
        event = PromotionChangeEvent(
            promotion_id=target.id,
            previous_promotion_id=previous_promotion.id if previous_promotion else None,
            observation_id=observation.id if observation else None,
            document_id=document_id,
            event_type=event_type,
            field_name=field_name,
            previous_value=_jsonable(previous_value),
            new_value=_jsonable(new_value),
            change_impact=max(0.0, min(1.0, float(impact or 0.0))),
            observed_at=observed_at,
            event_fingerprint=fingerprint,
        )
        db.add(event)
        db.flush()
        events.append(event)

    if created:
        add_event(event_type="CREATED", new_value={"promotion_id": str(promotion.id)})
    for change in changes or []:
        add_event(
            event_type=str(change.get("event_type", "TERMS_CHANGED")),
            field_name=change.get("field"),
            previous_value=change.get("previous_value"),
            new_value=change.get("new_value"),
            impact=change_impact,
        )

    if superseded_promotion is not None:
        add_event(
            event_type="SUPERSEDED",
            new_value={"superseded_by_promotion_id": str(promotion.id)},
            event_promotion=superseded_promotion,
            previous_promotion=promotion,
        )

    return events
