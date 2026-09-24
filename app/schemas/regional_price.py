from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict
import uuid


class RegionalPriceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    promotion_id: uuid.UUID
    geography: Optional[str] = None
    geography_source_text: Optional[str] = None
    retailer: Optional[str] = None
    channel: Optional[str] = None
    regular_price: Optional[Decimal] = None
    promo_price: Optional[Decimal] = None
    currency: str
    minimum_purchase_quantity: Optional[int] = None
    minimum_purchase_amount: Optional[Decimal] = None
    captured_at: datetime
    last_verified_at: Optional[datetime] = None
    evidence_text: Optional[str] = None
    source_url: Optional[str] = None
