from __future__ import annotations

from uuid import UUID
from typing import Optional
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.source import SourceRegistry, SourceUrl
from app.services.url_security import validate_public_url

LIFECYCLE_TRANSITIONS = {
    "DISCOVERED": {"CANDIDATE", "DISABLED"},
    "CANDIDATE": {"ASSESSED", "DISABLED"},
    "ASSESSED": {"APPROVED", "CANDIDATE", "DISABLED"},
    "APPROVED": {"ACTIVE", "MANUAL_ONLY", "DISABLED", "WARNING", "STALE", "BLOCKED"},
    "ACTIVE": {"WARNING", "STALE", "BLOCKED", "MANUAL_ONLY", "DISABLED"},
    "WARNING": {"ACTIVE", "STALE", "BLOCKED", "MANUAL_ONLY", "DISABLED"},
    "STALE": {"ACTIVE", "WARNING", "BLOCKED", "MANUAL_ONLY", "DISABLED"},
    "BLOCKED": {"APPROVED", "ACTIVE", "MANUAL_ONLY", "DISABLED"},
    "MANUAL_ONLY": {"APPROVED", "ACTIVE", "DISABLED"},
    "DISABLED": {"CANDIDATE", "ASSESSED", "APPROVED"},
}
BLOCKED_ACCESS = {"BLOCKED", "LOGIN_REQUIRED", "CAPTCHA_REQUIRED", "PAYWALL"}

def transition_source(source: SourceRegistry, target: str) -> None:
    current = source.lifecycle_status
    if target == current:
        return
    if target not in LIFECYCLE_TRANSITIONS.get(current, set()):
        raise HTTPException(status_code=409, detail=f"Invalid source lifecycle transition: {current} -> {target}")
    if target == "ACTIVE":
        if not source.adapter_key:
            raise HTTPException(status_code=422, detail="An explicit adapter_key is required before activation")
        if source.access_status in BLOCKED_ACCESS:
            raise HTTPException(status_code=409, detail=f"Source access status {source.access_status} cannot be activated")
    source.lifecycle_status = target
    source.is_active = target in {"APPROVED", "ACTIVE", "WARNING", "STALE"}

def get_source_or_404(db: Session, source_id: UUID) -> SourceRegistry:
    source = db.query(SourceRegistry).filter(SourceRegistry.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    return source

def register_url(db: Session, source: SourceRegistry, url: str, canonical_url: Optional[str], page_type: str, category: Optional[str], priority: int, frequency_minutes: int) -> SourceUrl:
    if source.lifecycle_status in {"BLOCKED", "DISABLED"}:
        raise HTTPException(status_code=409, detail="Cannot register a crawl target for a blocked or disabled source")
    safe_url = validate_public_url(url)
    safe_canonical = validate_public_url(canonical_url) if canonical_url else safe_url
    if db.query(SourceUrl).filter(SourceUrl.source_id == source.id, SourceUrl.url == safe_url).first():
        raise HTTPException(status_code=409, detail="URL is already registered for this source")
    target = SourceUrl(source_id=source.id, url=safe_url, canonical_url=safe_canonical, page_type=page_type, category=category, priority=priority, frequency_minutes=frequency_minutes, is_active=True)
    db.add(target)
    return target
