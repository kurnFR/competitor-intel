from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ScanRun(Base):
    """One execution of the crawl-and-extract pipeline (survives restarts, visible to every process)."""
    __tablename__ = "scan_runs"
    __table_args__ = (Index("idx_scan_runs_started", "started_at"), {"schema": "competitor_intel"})

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    trigger: Mapped[str] = mapped_column(String(20), nullable=False, default="CLI")      # MANUAL / SCHEDULED / CLI
    triggered_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="RUNNING")   # RUNNING / COMPLETED / FAILED
    summary: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
