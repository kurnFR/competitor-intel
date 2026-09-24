from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict
import uuid


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
    urls: List[SourceUrlOut] = []
    created_at: datetime
    updated_at: datetime
