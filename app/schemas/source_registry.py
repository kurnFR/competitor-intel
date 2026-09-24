from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field, HttpUrl
import uuid


class SourceUrlCreate(BaseModel):
    url: HttpUrl
    canonical_url: Optional[HttpUrl] = None
    page_type: str = "OTHER"
    category: Optional[str] = None
    priority: int = Field(default=5, ge=1, le=100)
    frequency_minutes: int = Field(default=360, ge=5, le=10080)


class SourceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    domain: str = Field(min_length=1, max_length=255)
    base_url: HttpUrl
    source_type: str = "RETAILER"
    adapter_key: Optional[str] = None
    tier: str = "TIER_3"
    category: Optional[str] = None
    priority: int = Field(default=5, ge=1, le=100)
    crawl_frequency_minutes: int = Field(default=360, ge=5, le=10080)


class SourceTransitionRequest(BaseModel):
    lifecycle_status: str
    access_status: Optional[str] = None
    adapter_key: Optional[str] = None


class SourceUrlOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    url: str
    canonical_url: Optional[str] = None
    page_type: str
    category: Optional[str] = None
    priority: int
    frequency_minutes: int
    is_active: bool
    last_crawled_at: Optional[datetime] = None
    last_changed_at: Optional[datetime] = None
    next_crawl_at: Optional[datetime] = None
    consecutive_failures: int
    last_http_status: Optional[int] = None


class SourceRegistryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    domain: str
    base_url: str
    source_type: str
    adapter_key: Optional[str] = None
    tier: str
    lifecycle_status: str
    access_mode: str
    access_status: str
    reliability_score: float
    country: str
    language: str
    category: Optional[str] = None
    crawl_frequency_minutes: int
    priority: int
    is_active: bool
    robots_allowed: bool
    last_crawled_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    last_error_at: Optional[datetime] = None
    consecutive_failures: int
    last_yield_count: int
    urls: List[SourceUrlOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class SourceHealthSummary(BaseModel):
    total_sources: int
    active_sources: int
    blocked_sources: int
    warning_sources: int
    failing_sources: int
    registered_urls: int
    due_urls: int
