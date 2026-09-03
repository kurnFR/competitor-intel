import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Company(Base):
    __tablename__ = "companies"
    __table_args__ = {"schema": "competitor"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    parent_company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    brands: Mapped[list["Brand"]] = relationship(back_populates="company")
    products: Mapped[list["Product"]] = relationship(back_populates="company")
    promotions: Mapped[list["Promotion"]] = relationship(back_populates="company")
    activities: Mapped[list["CompanyActivity"]] = relationship(back_populates="company")


class Brand(Base):
    __tablename__ = "brands"
    __table_args__ = {"schema": "competitor"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("competitor.companies.id"), nullable=True)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    company: Mapped[Company | None] = relationship(back_populates="brands")
    products: Mapped[list["Product"]] = relationship(back_populates="brand")


class Product(Base):
    __tablename__ = "products"
    __table_args__ = {"schema": "competitor"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    variant_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    brand_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("competitor.brands.id"), nullable=True)
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("competitor.companies.id"), nullable=True)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sub_category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sku: Mapped[str | None] = mapped_column(String(255), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pack_size_grams: Mapped[str | None] = mapped_column(String(50), nullable=True)
    units_per_carton: Mapped[int | None] = mapped_column(nullable=True)
    carton_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    brand: Mapped[Brand | None] = relationship(back_populates="products")
    company: Mapped[Company | None] = relationship(back_populates="products")
    promotions: Mapped[list["Promotion"]] = relationship(back_populates="product")
    activities: Mapped[list["CompanyActivity"]] = relationship(back_populates="product")


class Location(Base):
    __tablename__ = "locations"
    __table_args__ = {"schema": "competitor"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    country: Mapped[str | None] = mapped_column(String(150), nullable=True)
    province: Mapped[str | None] = mapped_column(String(150), nullable=True)
    city: Mapped[str | None] = mapped_column(String(150), nullable=True, index=True)
    region: Mapped[str | None] = mapped_column(String(150), nullable=True)
    latitude: Mapped[float | None] = mapped_column(nullable=True)
    longitude: Mapped[float | None] = mapped_column(nullable=True)

    retailers: Mapped[list["Retailer"]] = relationship(back_populates="location")
    activities: Mapped[list["CompanyActivity"]] = relationship(back_populates="location")


class Retailer(Base):
    __tablename__ = "retailers"
    __table_args__ = (
        CheckConstraint(
            "channel_type IN ('Retail', 'Modern Trade', 'General Trade', 'E-commerce', 'Wholesale', 'Distributor', 'Foodservice', 'N/A')",
            name="ck_retailers_verified_channel_type",
        ),
        {"schema": "competitor"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    retailer_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    channel_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    location_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("competitor.locations.id"), nullable=True)

    location: Mapped[Location | None] = relationship(back_populates="retailers")
    promotions: Mapped[list["Promotion"]] = relationship(back_populates="retailer")


class Promotion(Base):
    __tablename__ = "promotions"
    __table_args__ = {"schema": "competitor"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("competitor.products.id"), nullable=True)
    retailer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("competitor.retailers.id"), nullable=True)
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("competitor.companies.id"), nullable=True)
    promotion_type: Mapped[str | None] = mapped_column(String(150), nullable=True)
    regular_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    promo_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    discount_pct: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    buy_x_get_y: Mapped[str | None] = mapped_column(String(255), nullable=True)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    promo_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    evidence_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_timestamp: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    geographic_scope: Mapped[str | None] = mapped_column(String(255), nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    product: Mapped[Product | None] = relationship(back_populates="promotions")
    retailer: Mapped[Retailer | None] = relationship(back_populates="promotions")
    company: Mapped[Company | None] = relationship(back_populates="promotions")


class CompanyActivity(Base):
    __tablename__ = "company_activity"
    __table_args__ = {"schema": "competitor"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("competitor.companies.id"), nullable=True)
    activity_type: Mapped[str | None] = mapped_column(String(150), nullable=True)
    activity_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("competitor.locations.id"), nullable=True)
    related_product_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("competitor.products.id"), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    company: Mapped[Company | None] = relationship(back_populates="activities")
    location: Mapped[Location | None] = relationship(back_populates="activities")
    product: Mapped[Product | None] = relationship(back_populates="activities")
