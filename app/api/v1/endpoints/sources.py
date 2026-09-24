from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.db.session import get_db
from app.models.source import SourceRegistry, SourceUrl
from app.schemas.source_registry import SourceRegistryOut, SourceUrlOut, SourceHealthSummary, SourceCreate, SourceTransitionRequest, SourceUrlCreate
from app.services.source_registry import get_source_or_404, register_url, transition_source
from app.services.url_security import validate_public_url
from app.core.config import settings

router = APIRouter()


def _require_admin(request: Request) -> None:
    expected = settings.ADMIN_API_TOKEN
    if not expected:
        raise HTTPException(status_code=503, detail="Administrative API is not configured")
    if request.headers.get("X-Admin-Token") != expected:
        raise HTTPException(status_code=401, detail="Administrative authorization required")


@router.get("/", response_model=list[SourceRegistryOut])
def list_sources(lifecycle_status: Optional[str] = Query(None), access_status: Optional[str] = Query(None), source_type: Optional[str] = Query(None), active_only: bool = Query(False), q: Optional[str] = Query(None), db: Session = Depends(get_db)):
    query = db.query(SourceRegistry)
    if lifecycle_status: query = query.filter(SourceRegistry.lifecycle_status == lifecycle_status)
    if access_status: query = query.filter(SourceRegistry.access_status == access_status)
    if source_type: query = query.filter(SourceRegistry.source_type == source_type)
    if active_only: query = query.filter(SourceRegistry.is_active.is_(True))
    if q:
        keyword = f"%{q}%"
        query = query.filter(or_(SourceRegistry.name.ilike(keyword), SourceRegistry.domain.ilike(keyword), SourceRegistry.category.ilike(keyword)))
    return query.order_by(SourceRegistry.priority.asc(), SourceRegistry.name.asc()).all()


@router.post("/", response_model=SourceRegistryOut, status_code=201)
def discover_source(payload: SourceCreate, request: Request, db: Session = Depends(get_db)):
    _require_admin(request)
    safe_base = validate_public_url(str(payload.base_url), resolve_dns=False)
    if db.query(SourceRegistry).filter(SourceRegistry.domain == payload.domain.lower()).first():
        raise HTTPException(status_code=409, detail="A source with this domain already exists")
    source = SourceRegistry(name=payload.name, domain=payload.domain.lower(), base_url=safe_base, source_type=payload.source_type, adapter_key=payload.adapter_key, tier=payload.tier, lifecycle_status="DISCOVERED", is_active=False, category=payload.category, priority=payload.priority, crawl_frequency_minutes=payload.crawl_frequency_minutes)
    db.add(source); db.commit(); db.refresh(source)
    return source


@router.post("/{source_id}/transition", response_model=SourceRegistryOut)
def transition_source_status(source_id: UUID, payload: SourceTransitionRequest, request: Request, db: Session = Depends(get_db)):
    _require_admin(request)
    source = get_source_or_404(db, source_id)
    if payload.adapter_key is not None: source.adapter_key = payload.adapter_key
    if payload.access_status is not None: source.access_status = payload.access_status
    transition_source(source, payload.lifecycle_status)
    db.commit(); db.refresh(source)
    return source


@router.post("/{source_id}/urls", response_model=SourceUrlOut, status_code=201)
def add_source_url(source_id: UUID, payload: SourceUrlCreate, request: Request, db: Session = Depends(get_db)):
    _require_admin(request)
    source = get_source_or_404(db, source_id)
    target = register_url(db, source, str(payload.url), str(payload.canonical_url) if payload.canonical_url else None, payload.page_type, payload.category, payload.priority, payload.frequency_minutes)
    db.commit(); db.refresh(target)
    return target


@router.patch("/{source_id}/urls/{url_id}/disable", response_model=SourceUrlOut)
def disable_source_url(source_id: UUID, url_id: UUID, request: Request, db: Session = Depends(get_db)):
    _require_admin(request)
    source = get_source_or_404(db, source_id)
    target = db.query(SourceUrl).filter(SourceUrl.id == url_id, SourceUrl.source_id == source.id).first()
    if not target: raise HTTPException(status_code=404, detail="Source URL not found")
    target.is_active = False
    db.commit(); db.refresh(target)
    return target


@router.get("/urls/registry", response_model=list[SourceUrlOut])
def list_url_registry(source_id: Optional[str] = Query(None), page_type: Optional[str] = Query(None), active_only: bool = Query(False), due_only: bool = Query(False), db: Session = Depends(get_db)):
    from datetime import datetime, timezone
    query = db.query(SourceUrl)
    if source_id: query = query.filter(SourceUrl.source_id == source_id)
    if page_type: query = query.filter(SourceUrl.page_type == page_type)
    if active_only: query = query.filter(SourceUrl.is_active.is_(True))
    if due_only:
        now = datetime.now(timezone.utc)
        query = query.filter(SourceUrl.is_active.is_(True), (SourceUrl.next_crawl_at.is_(None)) | (SourceUrl.next_crawl_at <= now))
    return query.order_by(SourceUrl.priority.asc(), SourceUrl.next_crawl_at.asc().nullsfirst()).limit(1000).all()


@router.get("/health-summary", response_model=SourceHealthSummary)
def source_health_summary(db: Session = Depends(get_db)):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    total = db.query(SourceRegistry).count()
    active = db.query(SourceRegistry).filter(SourceRegistry.lifecycle_status == "ACTIVE", SourceRegistry.is_active.is_(True)).count()
    blocked = db.query(SourceRegistry).filter(SourceRegistry.access_status.in_(["BLOCKED", "LOGIN_REQUIRED", "CAPTCHA_REQUIRED", "PAYWALL"])).count()
    warning = db.query(SourceRegistry).filter(SourceRegistry.lifecycle_status.in_(["WARNING", "STALE"])).count()
    failing = db.query(SourceRegistry).filter(SourceRegistry.consecutive_failures > 0).count()
    urls = db.query(SourceUrl).count()
    due = db.query(SourceUrl).filter(SourceUrl.is_active.is_(True), (SourceUrl.next_crawl_at.is_(None)) | (SourceUrl.next_crawl_at <= now)).count()
    return SourceHealthSummary(total_sources=total, active_sources=active, blocked_sources=blocked, warning_sources=warning, failing_sources=failing, registered_urls=urls, due_urls=due)


@router.get("/{source_id}", response_model=SourceRegistryOut)
def get_source(source_id: UUID, db: Session = Depends(get_db)):
    return get_source_or_404(db, source_id)


@router.get("/{source_id}/urls", response_model=list[SourceUrlOut])
def list_source_urls(source_id: UUID, active_only: bool = Query(False), due_only: bool = Query(False), db: Session = Depends(get_db)):
    source = get_source_or_404(db, source_id)
    query = db.query(SourceUrl).filter(SourceUrl.source_id == source.id)
    if active_only: query = query.filter(SourceUrl.is_active.is_(True))
    if due_only:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        query = query.filter(SourceUrl.is_active.is_(True), (SourceUrl.next_crawl_at.is_(None)) | (SourceUrl.next_crawl_at <= now))
    return query.order_by(SourceUrl.priority.asc(), SourceUrl.next_crawl_at.asc().nullsfirst()).all()
