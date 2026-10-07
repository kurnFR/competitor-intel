"""Manage crawl sources (which websites are scanned). Administrators only.

Lifecycle (PRD 6): a source is added as a CANDIDATE and is never crawled until an administrator APPROVES it with an
explicit adapter. Rejected or paused sources are never crawled either.
"""
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import Principal, client_ip, require_role
from app.db.session import get_db
from app.models.source import SourceRegistry
from app.services import auth as auth_service
from app.services.crawler.manager import ADAPTER_LABELS, ADAPTERS
from app.services.source_health import compute_health
from app.services.sources import validate_source_url

router = APIRouter()
SOURCE_TYPES = ("RETAILER", "PROMOTION_AGGREGATOR", "BRAND_SITE")
admin = Depends(require_role("ADMIN"))
MIN_FREQUENCY, MAX_FREQUENCY = 15, 10080


class SourceIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    base_url: str = Field(min_length=8, max_length=2000)
    source_type: str = "RETAILER"
    adapter_key: str = "generic_catalog"
    reliability_score: float = Field(default=0.85, ge=0.1, le=1.0)


class SourcePatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    is_active: Optional[bool] = None
    reliability_score: Optional[float] = Field(default=None, ge=0.1, le=1.0)
    crawl_frequency_minutes: Optional[int] = Field(default=None, ge=MIN_FREQUENCY, le=MAX_FREQUENCY)
    adapter_key: Optional[str] = None


class ApproveIn(BaseModel):
    adapter_key: Optional[str] = None


class SourceOut(BaseModel):
    id: UUID
    name: str
    domain: str
    base_url: str
    source_type: str
    adapter_key: Optional[str]
    approval_status: str
    reliability_score: float
    crawl_frequency_minutes: int
    is_active: bool
    last_crawled_at: Optional[datetime]
    last_success_at: Optional[datetime]
    last_processed_at: Optional[datetime]
    last_error_at: Optional[datetime]
    health: str


_health = compute_health      # kept under its old name for the other modules that import it


def _out(s: SourceRegistry, now: datetime) -> SourceOut:
    return SourceOut(
        id=s.id, name=s.name, domain=s.domain, base_url=s.base_url, source_type=s.source_type, adapter_key=s.adapter_key,
        approval_status=s.approval_status, reliability_score=s.reliability_score, crawl_frequency_minutes=s.crawl_frequency_minutes,
        is_active=s.is_active, last_crawled_at=s.last_crawled_at, last_success_at=s.last_success_at,
        last_processed_at=s.last_processed_at, last_error_at=s.last_error_at, health=_health(s, now))


def _check_adapter(key: Optional[str]) -> None:
    if key is not None and key not in ADAPTERS:
        raise HTTPException(status_code=422, detail=f"Adapter must be one of: {', '.join(ADAPTERS)}.")


@router.get("/adapters")
def list_adapters(_: Principal = admin):
    return [{"key": k, "label": ADAPTER_LABELS.get(k, k)} for k in ADAPTERS]


@router.get("/", response_model=List[SourceOut])
def list_sources(_: Principal = admin, db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    return [_out(s, now) for s in db.query(SourceRegistry).order_by(SourceRegistry.approval_status, SourceRegistry.name).all()]


@router.post("/", response_model=SourceOut, status_code=201)
def add_source(body: SourceIn, request: Request, principal: Principal = admin, db: Session = Depends(get_db)):
    """Adds a CANDIDATE. Nothing is crawled until it is approved."""
    if body.source_type not in SOURCE_TYPES:
        raise HTTPException(status_code=422, detail=f"Type must be one of {', '.join(SOURCE_TYPES)}.")
    _check_adapter(body.adapter_key)
    try:
        domain = validate_source_url(body.base_url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    if db.query(SourceRegistry).filter(SourceRegistry.base_url == body.base_url.strip()).first():
        raise HTTPException(status_code=409, detail="This address is already registered.")
    source = SourceRegistry(
        name=body.name.strip(), domain=domain.removeprefix("www."), base_url=body.base_url.strip(),
        source_type=body.source_type, tier="TIER_1" if body.source_type == "RETAILER" else "TIER_3",
        reliability_score=body.reliability_score, category=body.source_type, adapter_key=body.adapter_key,
        crawl_frequency_minutes=settings.CRAWL_INTERVAL_MINUTES, approval_status="CANDIDATE", is_active=False,
    )
    db.add(source)
    auth_service.audit(db, "source_added", username=principal.user.username, ip=client_ip(request),
                       detail={"name": source.name, "url": source.base_url, "adapter": source.adapter_key})
    db.commit()
    return _out(source, datetime.now(timezone.utc))


def _get(db: Session, source_id: UUID) -> SourceRegistry:
    source = db.get(SourceRegistry, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found.")
    return source


@router.post("/{source_id}/approve", response_model=SourceOut)
def approve_source(source_id: UUID, body: ApproveIn, request: Request, principal: Principal = admin, db: Session = Depends(get_db)):
    source = _get(db, source_id)
    if body.adapter_key is not None:
        _check_adapter(body.adapter_key)
        source.adapter_key = body.adapter_key
    if not source.adapter_key or source.adapter_key not in ADAPTERS:
        raise HTTPException(status_code=422, detail="Choose a supported adapter before approving this source.")
    source.approval_status, source.is_active = "APPROVED", True
    auth_service.audit(db, "source_approved", username=principal.user.username, ip=client_ip(request),
                       detail={"name": source.name, "adapter": source.adapter_key})
    db.commit()
    return _out(source, datetime.now(timezone.utc))


@router.post("/{source_id}/reject", response_model=SourceOut)
def reject_source(source_id: UUID, request: Request, principal: Principal = admin, db: Session = Depends(get_db)):
    source = _get(db, source_id)
    source.approval_status, source.is_active = "REJECTED", False
    auth_service.audit(db, "source_rejected", username=principal.user.username, ip=client_ip(request),
                       detail={"name": source.name})
    db.commit()
    return _out(source, datetime.now(timezone.utc))


@router.patch("/{source_id}", response_model=SourceOut)
def update_source(source_id: UUID, body: SourcePatch, request: Request, principal: Principal = admin,
                  db: Session = Depends(get_db)):
    source = _get(db, source_id)
    changes = body.model_dump(exclude_unset=True)
    _check_adapter(changes.get("adapter_key"))
    if changes.get("is_active") and source.approval_status != "APPROVED":
        raise HTTPException(status_code=409, detail="Only an approved source can be resumed. Approve it first.")
    for key, value in changes.items():
        setattr(source, key, value)
    auth_service.audit(db, "source_updated", username=principal.user.username, ip=client_ip(request),
                       detail={"name": source.name, **changes})
    db.commit()
    return _out(source, datetime.now(timezone.utc))
