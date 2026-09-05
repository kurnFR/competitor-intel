"""Persist conservative entity-resolution outcomes for human review."""

from __future__ import annotations

from typing import Iterable

from sqlalchemy.orm import Session

from app.models.resolution import ReviewQueue
from app.services.entity_resolution.resolver import ResolutionResult


def persist_resolution_reviews(
    db: Session,
    *,
    observation_id,
    promotion_id,
    resolutions: Iterable[tuple[str, str | None, ResolutionResult]],
) -> int:
    """Persist unresolved/ambiguous entity decisions without auto-creating entities.

    Existing pending items for the same observation/entity type are reused so
    repeated pipeline runs do not create a review-queue explosion.
    """
    created = 0
    for entity_type, source_value, result in resolutions:
        if result.status == "RESOLVED":
            continue
        if not source_value and result.status == "UNRESOLVED":
            continue

        existing = (
            db.query(ReviewQueue)
            .filter(
                ReviewQueue.observation_id == observation_id,
                ReviewQueue.entity_type == entity_type,
                ReviewQueue.status == "PENDING",
            )
            .first()
        )
        if existing is not None:
            continue

        source_label = source_value.strip() if source_value else "(missing)"
        reason = result.reason or f"Entity resolution status: {result.status}"
        if result.method:
            reason = f"{reason}; method={result.method}"

        db.add(
            ReviewQueue(
                entity_type=entity_type,
                entity_id=None,
                candidate_entity_id=result.candidate_id,
                promotion_id=promotion_id,
                observation_id=observation_id,
                reason=f"Source value '{source_label}': {reason}",
                confidence=result.confidence,
                priority=2 if result.status == "REVIEW" else 1,
                status="PENDING",
            )
        )
        created += 1

    if created:
        db.flush()
    return created
