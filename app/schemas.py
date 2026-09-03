from datetime import datetime
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, Field, model_validator


class CompanyCreate(BaseModel):
    company_name: str
    parent_company: str | None = None
    industry: str | None = None
    company_type: str | None = None
    website: str | None = None


class CompanyRead(CompanyCreate):
    id: UUID
    created_at: datetime


class ProductCreate(BaseModel):
    product_name: str
    brand_id: UUID | None = None
    company_id: UUID | None = None
    category: str | None = None
    sub_category: str | None = None
    sku: str | None = None
    unit: str | None = None


class ProductRead(ProductCreate):
    id: UUID
    created_at: datetime


class PromotionCreate(BaseModel):
    product_id: UUID | None = None
    retailer_id: UUID | None = None
    company_id: UUID | None = None
    promotion_type: str | None = None
    regular_price: float | None = None
    promo_price: float | None = None
    discount_pct: float | None = None
    buy_x_get_y: str | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    promo_status: str | None = Field(default="active")
    source_url: AnyHttpUrl | None = None
    source_type: str | None = None
    evidence_text: str | None = None
    source_timestamp: datetime | None = None
    geographic_scope: str | None = None
    confidence_score: float | None = None

    @model_validator(mode="after")
    def validate_evidence(self):
        if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
            raise ValueError("valid_to must be on or after valid_from")
        if self.confidence_score is not None and not 0 <= self.confidence_score <= 1:
            raise ValueError("confidence_score must be between 0 and 1")
        if self.confidence_score and not (self.source_url and self.source_timestamp and self.evidence_text):
            raise ValueError("A confident promotion requires source_url, source_timestamp, and evidence_text")
        return self


class PromotionRead(PromotionCreate):
    id: UUID
    created_at: datetime


class SearchResult(BaseModel):
    type: str
    name: str
    id: UUID
    match: str
    score: float = 0.0
