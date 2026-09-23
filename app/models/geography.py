import uuid
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import String, Text, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base


class Geography(Base):
    __tablename__ = "geographies"
    __table_args__ = (
        Index("idx_geographies_parent", "parent_id"),
        Index("idx_geographies_type_name", "geography_type", "normalized_name"),
        {"schema": "competitor_intel"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    geography_type: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)
    country_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("competitor_intel.geographies.id", ondelete="RESTRICT"), nullable=True)
    source_system: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    parent: Mapped[Optional["Geography"]] = relationship("Geography", remote_side=[id], back_populates="children")
    children: Mapped[List["Geography"]] = relationship("Geography", back_populates="parent")
