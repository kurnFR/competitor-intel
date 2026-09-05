from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.models.entity import Competitor, Brand, Product, Retailer
import uuid
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import String, Text, Float, Integer, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base


class PromotionObservation(Base):
    __tablename__ = "promotion_observations"
    __table_args__ = {"schema": "competitor_intel"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("competitor_intel.crawl_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    promotion_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("competitor_intel.promotions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    raw_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extracted_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    ai_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    extraction_model: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    extraction_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    extracted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    extraction_raw_response_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    extraction_rejected_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    promotion: Mapped[Optional["Promotion"]] = relationship("Promotion", back_populates="observations")


class Promotion(Base):
    __tablename__ = "promotions"
    __table_args__ = (
        Index("idx_promotions_status", "status"),
        Index("idx_promotions_end_date", "end_date"),
        Index("idx_promotions_last_seen", "last_seen_at"),
        Index("idx_promotions_category", "category"),
        Index("idx_promotions_rank_score", "rank_score"),
        Index("idx_promotions_active_top", "status", "end_date", "last_seen_at", "rank_score"),
        {"schema": "competitor_intel"}
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competitor_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("competitor_intel.competitors.id", ondelete="SET NULL"), nullable=True, index=True)
    brand_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("competitor_intel.brands.id", ondelete="SET NULL"), nullable=True, index=True)
    product_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("competitor_intel.products.id", ondelete="SET NULL"), nullable=True, index=True)
    retailer_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("competitor_intel.retailers.id", ondelete="SET NULL"), nullable=True, index=True)

    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sku: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    pack_size: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    category: Mapped[str] = mapped_column(String(100), default="BISCUIT")

    regular_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    promo_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="IDR")
    discount_percentage: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    promotion_type: Mapped[str] = mapped_column(String(50), nullable=False, default="DISCOUNT")
    buy_quantity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    free_quantity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    bundle_quantity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cashback_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    voucher_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    minimum_purchase_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    minimum_purchase_quantity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    gift_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    promotion_title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    promotion_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    start_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    end_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    channel: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    geography: Mapped[str] = mapped_column(String(50), default="Indonesia")

    status: Mapped[str] = mapped_column(String(50), default="ACTIVE")
    source_reliability: Mapped[float] = mapped_column(Float, default=0.8)
    ai_confidence: Mapped[float] = mapped_column(Float, default=0.8)
    rank_score: Mapped[float] = mapped_column(Float, default=0.0)

    identity_fingerprint: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    identity_version: Mapped[str] = mapped_column(String(20), default="v1", nullable=False)
    source_identity_fingerprint: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)

    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    competitor: Mapped[Optional["Competitor"]] = relationship("app.models.entity.Competitor")
    brand: Mapped[Optional["Brand"]] = relationship("app.models.entity.Brand")
    retailer: Mapped[Optional["Retailer"]] = relationship("app.models.entity.Retailer")
    product: Mapped[Optional["Product"]] = relationship("app.models.entity.Product")
    observations: Mapped[List["PromotionObservation"]] = relationship("PromotionObservation", back_populates="promotion")
    evidence_items: Mapped[List["PromotionEvidence"]] = relationship("PromotionEvidence", back_populates="promotion", cascade="all, delete-orphan")


class PromotionEvidence(Base):
    __tablename__ = "promotion_evidence"
    __table_args__ = {"schema": "competitor_intel"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    promotion_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("competitor_intel.promotions.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("competitor_intel.crawl_documents.id", ondelete="SET NULL"), nullable=True)
    evidence_type: Mapped[str] = mapped_column(String(50), default="TEXT")
    evidence_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    promotion: Mapped["Promotion"] = relationship("Promotion", back_populates="evidence_items")
