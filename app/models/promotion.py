from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.models.entity import Competitor, Brand, Product, Retailer
import uuid
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import String, Text, Float, Integer, DateTime, ForeignKey, Index, Numeric, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base


class PromotionObservation(Base):
    __tablename__ = "promotion_observations"
    __table_args__ = (
        Index("idx_promotion_observations_document", "document_id"),
        Index("idx_promotion_observations_verified", "last_verified_at"),
        {"schema": "competitor_intel"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("competitor_intel.crawl_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    raw_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extracted_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    ai_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    verification_status: Mapped[str] = mapped_column(String(30), default="UNVERIFIED", index=True)
    quality_status: Mapped[str] = mapped_column(String(30), default="PENDING", index=True)
    valid_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Promotion(Base):
    __tablename__ = "promotions"
    __table_args__ = (
        Index("idx_promotions_status", "status"),
        Index("idx_promotions_end_date", "end_date"),
        Index("idx_promotions_last_verified", "last_verified_at"),
        Index("idx_promotions_category", "category"),
        Index("idx_promotions_rank_score", "rank_score"),
        Index("idx_promotions_active_top", "status", "end_date", "last_verified_at", "rank_score"),
        {"schema": "competitor_intel"},
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

    regular_price: Mapped[Optional[float]] = mapped_column(Numeric(18, 2), nullable=True)
    promo_price: Mapped[Optional[float]] = mapped_column(Numeric(18, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="IDR")
    discount_percentage: Mapped[Optional[float]] = mapped_column(Numeric(7, 3), nullable=True)

    promotion_type: Mapped[str] = mapped_column(String(50), nullable=False, default="DISCOUNT")
    buy_quantity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    free_quantity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    bundle_quantity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cashback_amount: Mapped[Optional[float]] = mapped_column(Numeric(18, 2), nullable=True)
    voucher_amount: Mapped[Optional[float]] = mapped_column(Numeric(18, 2), nullable=True)
    minimum_purchase_amount: Mapped[Optional[float]] = mapped_column(Numeric(18, 2), nullable=True)
    minimum_purchase_quantity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    gift_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    promotion_title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    promotion_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    start_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    end_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    channel: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    legacy_geography: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    status: Mapped[str] = mapped_column(String(50), default="PENDING_REVIEW", index=True)
    source_reliability: Mapped[float] = mapped_column(Float, default=0.8)
    ai_confidence: Mapped[float] = mapped_column(Float, default=0.8)
    rank_score: Mapped[float] = mapped_column(Float, default=0.0)

    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    competitor: Mapped[Optional["Competitor"]] = relationship("app.models.entity.Competitor")
    brand: Mapped[Optional["Brand"]] = relationship("app.models.entity.Brand")
    retailer: Mapped[Optional["Retailer"]] = relationship("app.models.entity.Retailer")
    product: Mapped[Optional["Product"]] = relationship("app.models.entity.Product")
    evidence_items: Mapped[List["PromotionEvidence"]] = relationship("PromotionEvidence", back_populates="promotion", cascade="all, delete-orphan")
    geographies: Mapped[List["PromotionGeography"]] = relationship("PromotionGeography", back_populates="promotion", cascade="all, delete-orphan")


class PromotionEvidence(Base):
    __tablename__ = "promotion_evidence"
    __table_args__ = {"schema": "competitor_intel"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    promotion_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("competitor_intel.promotions.id", ondelete="CASCADE"), nullable=False, index=True)
    observation_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("competitor_intel.promotion_observations.id", ondelete="SET NULL"), nullable=True, index=True)
    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("competitor_intel.crawl_documents.id", ondelete="SET NULL"), nullable=True)
    evidence_type: Mapped[str] = mapped_column(String(50), default="TEXT")
    evidence_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    promotion: Mapped["Promotion"] = relationship("Promotion", back_populates="evidence_items")


class PromotionGeography(Base):
    __tablename__ = "promotion_geographies"
    __table_args__ = (
        Index("idx_promotion_geographies_promotion", "promotion_id"),
        Index("idx_promotion_geographies_geography", "geography_id"),
        {"schema": "competitor_intel"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    promotion_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("competitor_intel.promotions.id", ondelete="CASCADE"), nullable=False)
    geography_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("competitor_intel.geographies.id", ondelete="RESTRICT"), nullable=False)
    inclusion_type: Mapped[str] = mapped_column(String(20), default="INCLUDE")
    source_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    promotion: Mapped["Promotion"] = relationship("Promotion", back_populates="geographies")
