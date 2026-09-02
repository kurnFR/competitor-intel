import uuid
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import String, Text, Integer, Float, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base


class SourceRegistry(Base):
    __tablename__ = "source_registry"
    __table_args__ = {"schema": "competitor_intel"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), default="RETAILER")
    tier: Mapped[str] = mapped_column(String(20), default="TIER_1")
    reliability_score: Mapped[float] = mapped_column(Float, default=1.0)
    country: Mapped[str] = mapped_column(String(10), default="ID")
    language: Mapped[str] = mapped_column(String(10), default="id")
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    crawl_frequency_minutes: Mapped[int] = mapped_column(Integer, default=60)
    priority: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    robots_allowed: Mapped[bool] = mapped_column(Boolean, default=True)
    last_crawled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    crawl_jobs: Mapped[List["CrawlJob"]] = relationship("CrawlJob", back_populates="source", cascade="all, delete-orphan")
    documents: Mapped[List["CrawlDocument"]] = relationship("CrawlDocument", back_populates="source", cascade="all, delete-orphan")


class CrawlJob(Base):
    __tablename__ = "crawl_jobs"
    __table_args__ = {"schema": "competitor_intel"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("competitor_intel.source_registry.id", ondelete="CASCADE"), nullable=False, index=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    job_type: Mapped[str] = mapped_column(String(50), default="CATALOG")
    status: Mapped[str] = mapped_column(String(50), default="QUEUED", index=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    http_status: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    source: Mapped["SourceRegistry"] = relationship("SourceRegistry", back_populates="crawl_jobs")
    documents: Mapped[List["CrawlDocument"]] = relationship("CrawlDocument", back_populates="crawl_job")


class CrawlDocument(Base):
    __tablename__ = "crawl_documents"
    __table_args__ = (
        Index("idx_crawl_documents_url", "url"),
        Index("idx_crawl_documents_content_hash", "content_hash"),
        {"schema": "competitor_intel"}
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    crawl_job_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("competitor_intel.crawl_jobs.id", ondelete="SET NULL"), nullable=True, index=True)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("competitor_intel.source_registry.id", ondelete="CASCADE"), nullable=False, index=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    document_type: Mapped[str] = mapped_column(String(20), default="HTML")
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_content_uri: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    text_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    language: Mapped[str] = mapped_column(String(10), default="id")
    http_status: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    source: Mapped["SourceRegistry"] = relationship("SourceRegistry", back_populates="documents")
    crawl_job: Mapped[Optional["CrawlJob"]] = relationship("CrawlJob", back_populates="documents")
