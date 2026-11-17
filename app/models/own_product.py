from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class OwnProduct(Base):
    """One of our own products, used to compare against competitor promotions."""
    __tablename__ = "own_products"
    __table_args__ = (Index("idx_own_products_category", "category"), {"schema": "competitor_intel"})

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sku: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    brand: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False, default="BISCUIT")
    pack_size: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    pack_grams: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    regular_price: Mapped[float] = mapped_column(Float, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Promotional pricing & mechanics
    promo_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    promo_type: Mapped[str] = mapped_column(String(50), nullable=False, default="REGULAR", server_default="REGULAR")
    promo_start_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    promo_end_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    promo_mechanic: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    buy_quantity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    free_quantity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    buy_x: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    get_y: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    def __init__(self, **kwargs):
        kwargs.setdefault("id", uuid.uuid4())
        kwargs.setdefault("category", "BISCUIT")
        kwargs.setdefault("is_active", True)
        kwargs.setdefault("promo_type", "REGULAR")
        kwargs.setdefault("created_at", _now())
        kwargs.setdefault("updated_at", _now())
        if "buy_x" in kwargs and kwargs.get("buy_quantity") is None:
            kwargs["buy_quantity"] = kwargs["buy_x"]
        elif "buy_quantity" in kwargs and kwargs.get("buy_x") is None:
            kwargs["buy_x"] = kwargs["buy_quantity"]
        if "get_y" in kwargs and kwargs.get("free_quantity") is None:
            kwargs["free_quantity"] = kwargs["get_y"]
        elif "free_quantity" in kwargs and kwargs.get("get_y") is None:
            kwargs["get_y"] = kwargs["free_quantity"]
        super().__init__(**kwargs)

    @property
    def has_active_promo(self) -> bool:
        """True if promo_price is set and current time is within promo_start_date and promo_end_date (if specified)."""
        if self.promo_price is None:
            return False
        now = datetime.now(timezone.utc)
        if self.promo_start_date and now < self.promo_start_date:
            return False
        if self.promo_end_date and now > self.promo_end_date:
            return False
        return True
