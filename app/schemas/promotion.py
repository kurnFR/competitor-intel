from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict
import uuid


class EvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    evidence_type: str
    evidence_text: str
    source_url: Optional[str] = None
    captured_at: datetime


class PromotionChangeEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    promotion_id: uuid.UUID
    previous_promotion_id: Optional[uuid.UUID] = None
    observation_id: Optional[uuid.UUID] = None
    document_id: Optional[uuid.UUID] = None
    event_type: str
    field_name: Optional[str] = None
    previous_value: Optional[Dict[str, Any]] = None
    new_value: Optional[Dict[str, Any]] = None
    change_impact: float
    observed_at: datetime


class Top10PromotionItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    rank: int
    product_name: str
    brand: Optional[str] = None
    competitor: Optional[str] = None
    category: str
    pack_size: Optional[str] = None
    retailer: Optional[str] = None
    outlet: Optional[str] = None
    channel: Optional[str] = None
    geography: Optional[str] = None
    promotion_type: str
    buy_quantity: Optional[int] = None
    free_quantity: Optional[int] = None
    regular_price: Optional[float] = None
    promo_price: Optional[float] = None
    discount_percentage: Optional[float] = None
    effective_discount: Optional[float] = None
    valid_until: Optional[str] = None
    valid_from: Optional[str] = None
    rank_score: float
    ai_confidence: float
    source_reliability: float
    evidence_quote: Optional[str] = None
    source_url: Optional[str] = None
    source_status: str = "Unverified source"
    last_verified: datetime


class Top10Response(BaseModel):
    generated_at: str
    count: int
    promotions: List[Top10PromotionItem]


class PromotionDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    product_name: str
    brand: Optional[str] = None
    competitor: Optional[str] = None
    category: str
    pack_size: Optional[str] = None
    retailer: Optional[str] = None
    channel: Optional[str] = None
    promotion_type: str
    buy_quantity: Optional[int] = None
    free_quantity: Optional[int] = None
    regular_price: Optional[float] = None
    promo_price: Optional[float] = None
    discount_percentage: Optional[float] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    status: str
    supersedes_promotion_id: Optional[uuid.UUID] = None
    source_reliability: float
    ai_confidence: float
    rank_score: float
    first_seen_at: datetime
    last_seen_at: datetime
    evidence_items: List[EvidenceOut] = []
    change_events: List[PromotionChangeEventOut] = []


class StatsResponse(BaseModel):
    active_promotions: int
    competitors_tracked: int
    brands_tracked: int
    retailers_tracked: int
    expiring_soon_7days: int
    type_distribution: Dict[str, int]
    retailer_distribution: Dict[str, int]
