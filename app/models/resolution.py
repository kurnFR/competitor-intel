import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Text, Float, Integer, DateTime, Index, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class EntityMapping(Base):
    __tablename__ = "entity_mapping"
    __table_args__ = (
        Index("idx_entity_mapping_type_val", "entity_type", "source_value"),
        Index("idx_entity_mapping_type_normalized", "entity_type", "normalized_source_value"),
        {"schema": "competitor_intel"}
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_value: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_source_value: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    canonical_entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    match_method: Mapped[str] = mapped_column(String(50), default="EXACT")
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    resolution_status: Mapped[str] = mapped_column(String(30), default="APPROVED")
    review_queue_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("competitor_intel.review_queue.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class ReviewQueue(Base):
    __tablename__ = "review_queue"
    __table_args__ = (
        Index("idx_review_queue_status", "status"),
        Index("idx_review_queue_promotion", "promotion_id"),
        Index("idx_review_queue_observation", "observation_id"),
        {"schema": "competitor_intel"}
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    candidate_entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    promotion_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    observation_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(50), default="PENDING")
    assigned_to: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    review_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
