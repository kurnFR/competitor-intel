from datetime import datetime
from typing import Optional
from pydantic import BaseModel
import uuid


class ReviewQueueItem(BaseModel):
    id: uuid.UUID
    product_name: str
    brand: Optional[str] = None
    competitor: Optional[str] = None
    category: str
    retailer: Optional[str] = None
    channel: Optional[str] = None
    geography: Optional[str] = None
    promotion_type: str
    regular_price: Optional[float] = None
    promo_price: Optional[float] = None
    discount_percentage: Optional[float] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    ai_confidence: float
    source_reliability: float
    last_seen_at: datetime
    evidence_quote: Optional[str] = None
    source_url: Optional[str] = None


class ReviewDecision(BaseModel):
    decision: str
    reason: Optional[str] = None


class ReviewDecisionOut(BaseModel):
    id: uuid.UUID
    status: str
    reviewed_at: datetime
    reason: Optional[str] = None
