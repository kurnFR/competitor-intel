"""Manage crawl sources (which websites are scanned). Administrators only."""
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import Principal, client_ip, require_role
from app.db.session import get_db
from app.models.source import SourceRegistry
from app.services import auth as auth_service
from app.services.sources import validate_source_url

router = APIRouter()
SOURCE_TYPES = ("RETAILER", "PROMOTION_AGGREGATOR", "BRAND_SITE")
admin = Depends(require_role("ADMIN"))


class SourceIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    base_url: str = Field(min_length=8, max_length=2000)
    source_type: str = "RETAILER"
    reliability_score: float = Field(default=0.85, ge=0.1, le=1.0)


class SourcePatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    is_active: Optional[bool] = None
    reliability_score: Optional[float] = Field(default=None, ge=0.1, le=1.0)


class SourceOut(BaseModel):
    id: UUID
    name: str
    domain: str
    base_url: str
    source_type: str
    reliability_score: float
    is_active: bool
    last_crawled_at: Optional[datetime]
    last_success_at: Optional[datetime]
    last_error_at: Optional[datetime]
    health: str


def _health(s: SourceRegistry, now: datetime) -> str:
    if not s.is_active:
        return "DISABLED"
    if s.last_crawled_at is None:
        return "NEVER_SCANNED"
    if s.last_error_at and (s.last_success_at is None or s.last_error_at > s.last_success_at):
        return "FAILING"
    if s.last_success_at and now - s.last_success_at > timedelta(days=3):
        return "STALE"
    return "OK"


def _out(s: SourceRegistry, now: datetime) -> SourceOut:
    return SourceOut(id=s.id, name=s.name, domain=s.domain, base_url=s.base_url, source_type=s.source_type,
                     reliability_score=s.reliability_score, is_active=s.is_active, last_crawled_at=s.last_crawled_at,
                     last_success_at=s.last_success_at, last_error_at=s.last_error_at, health=_health(s, now))


@router.get("/", response_model=List[SourceOut])
def list_sources(_: Principal = admin, db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    return [_out(s, now) for s in db.query(SourceRegistry).order_by(SourceRegistry.name).all()]


@router.post("/", response_model=SourceOut, status_code=201)
def add_source(body: SourceIn, request: Request, principal: Principal = admin, db: Session = Depends(get_db)):
    if body.source_type not in SOURCE_TYPES:
        raise HTTPException(status_code=422, detail=f"Type must be one of {', '.join(SOURCE_TYPES)}.")
    try:
        domain = validate_source_url(body.base_url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if db.query(SourceRegistry).filter(SourceRegistry.base_url == body.base_url.strip()).first():
        raise HTTPException(status_code=409, detail="This address is already registered.")
    source = SourceRegistry(
        name=body.name.strip(), domain=domain.removeprefix("www."), base_url=body.base_url.strip(),
        source_type=body.source_type, tier="TIER_1" if body.source_type == "RETAILER" else "TIER_3",
        reliability_score=body.reliability_score, category=body.source_type, is_active=True,
    )
    db.add(source)
    auth_service.audit(db, "source_added", username=principal.user.username, ip=client_ip(request),
                       detail={"name": source.name, "url": source.base_url})
    db.commit()
    return _out(source, datetime.now(timezone.utc))


@router.patch("/{source_id}", response_model=SourceOut)
def update_source(source_id: UUID, body: SourcePatch, request: Request, principal: Principal = admin,
                  db: Session = Depends(get_db)):
    source = db.get(SourceRegistry, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found.")
    changes = body.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(source, key, value)
    auth_service.audit(db, "source_updated", username=principal.user.username, ip=client_ip(request),
                       detail={"name": source.name, **changes})
    db.commit()
    return _out(source, datetime.now(timezone.utc))
