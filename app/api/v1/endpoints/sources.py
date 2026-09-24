from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.db.session import get_db
from app.models.source import SourceRegistry, SourceUrl
from app.schemas.source_registry import SourceRegistryOut, SourceUrlOut, SourceHealthSummary

router = APIRouter()


@router.get("/", response_model=list[SourceRegistryOut])
def list_sources(
    lifecycle_status: Optional[str] = Query(None),
    access_status: Optional[str] = Query(None),
    source_type: Optional[str] = Query(None),
    active_only: bool = Query(False),
    q: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(SourceRegistry)
    if lifecycle_status:
        query = query.filter(SourceRegistry.lifecycle_status == lifecycle_status)
    if access_status:
        query = query.filter(SourceRegistry.access_status == access_status)
    if source_type:
        query = query.filter(SourceRegistry.source_type == source_type)
    if active_only:
        query = query.filter(SourceRegistry.is_active.is_(True))
    if q:
        keyword = f"%{q}%"
        query = query.filter(or_(
            SourceRegistry.name.ilike(keyword),
            SourceRegistry.domain.ilike(keyword),
            SourceRegistry.category.ilike(keyword),
        ))
    sources = query.order_by(SourceRegistry.priority.asc(), SourceRegistry.name.asc()).all()
    return sources


@router.get("/urls/registry", response_model=list[SourceUrlOut])
def list_url_registry(
    source_id: Optional[str] = Query(None),
    page_type: Optional[str] = Query(None),
    active_only: bool = Query(False),
    due_only: bool = Query(False),
    db: Session = Depends(get_db),
):
    from datetime import datetime, timezone
    query = db.query(SourceUrl)
    if source_id:
        query = query.filter(SourceUrl.source_id == source_id)
    if page_type:
        query = query.filter(SourceUrl.page_type == page_type)
    if active_only:
        query = query.filter(SourceUrl.is_active.is_(True))
    if due_only:
        now = datetime.now(timezone.utc)
        query = query.filter(
            SourceUrl.is_active.is_(True),
            (SourceUrl.next_crawl_at.is_(None)) | (SourceUrl.next_crawl_at <= now),
        )
    return query.order_by(SourceUrl.priority.asc(), SourceUrl.next_crawl_at.asc().nullsfirst()).limit(1000).all()


@router.get("/health-summary", response_model=SourceHealthSummary)
def source_health_summary(db: Session = Depends(get_db)):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    total = db.query(SourceRegistry).count()
    active = db.query(SourceRegistry).filter(SourceRegistry.lifecycle_status == "ACTIVE", SourceRegistry.is_active.is_(True)).count()
    blocked = db.query(SourceRegistry).filter(SourceRegistry.access_status.in_([ "BLOCKED", "LOGIN_REQUIRED", "CAPTCHA_REQUIRED", "PAYWALL" ])).count()
    warning = db.query(SourceRegistry).filter(SourceRegistry.lifecycle_status.in_([ "WARNING", "STALE" ])).count()
    failing = db.query(SourceRegistry).filter(SourceRegistry.consecutive_failures > 0).count()
    urls = db.query(SourceUrl).count()
    due = db.query(SourceUrl).filter(SourceUrl.is_active.is_(True), (SourceUrl.next_crawl_at.is_(None)) | (SourceUrl.next_crawl_at <= now)).count()
    return SourceHealthSummary(total_sources=total, active_sources=active, blocked_sources=blocked, warning_sources=warning, failing_sources=failing, registered_urls=urls, due_urls=due)


@router.get("/{source_id}", response_model=SourceRegistryOut)
def get_source(source_id: str, db: Session = Depends(get_db)):
    source = db.query(SourceRegistry).filter(SourceRegistry.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    return source


@router.get("/{source_id}/urls", response_model=list[SourceUrlOut])
def list_source_urls(
    source_id: str,
    active_only: bool = Query(False),
    due_only: bool = Query(False),
    db: Session = Depends(get_db),
):
    source = db.query(SourceRegistry.id).filter(SourceRegistry.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    query = db.query(SourceUrl).filter(SourceUrl.source_id == source_id)
    if active_only:
        query = query.filter(SourceUrl.is_active.is_(True))
    if due_only:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        query = query.filter(
            SourceUrl.is_active.is_(True),
            (SourceUrl.next_crawl_at.is_(None)) | (SourceUrl.next_crawl_at <= now),
        )
    return query.order_by(SourceUrl.priority.asc(), SourceUrl.next_crawl_at.asc().nullsfirst()).all()
