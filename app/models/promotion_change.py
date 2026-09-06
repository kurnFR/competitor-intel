from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class PromotionChangeEvent(Base):
    __tablename__ = "promotion_change_events"
    __table_args__ = (
        UniqueConstraint("event_fingerprint", name="uq_promotion_change_event_fingerprint"),
        Index("idx_promotion_change_events_promotion_observed", "promotion_id", "observed_at"),
        Index("idx_promotion_change_events_type_observed", "event_type", "observed_at"),
        Index("idx_promotion_change_events_observation", "observation_id"),
        {"schema": "competitor_intel"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    promotion_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("competitor_intel.promotions.id", ondelete="CASCADE"),
        nullable=False,
    )
    previous_promotion_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("competitor_intel.promotions.id", ondelete="SET NULL"),
        nullable=True,
    )
    observation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("competitor_intel.promotion_observations.id", ondelete="SET NULL"),
        nullable=True,
    )
    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("competitor_intel.crawl_documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    field_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    previous_value: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    change_impact: Mapped[float] = mapped_column(default=0.0)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    promotion = relationship("Promotion", foreign_keys=[promotion_id])
    previous_promotion = relationship("Promotion", foreign_keys=[previous_promotion_id])
