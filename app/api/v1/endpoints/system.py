"""Setup self-check for administrators."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import Principal, require_role
from app.db.session import get_db
from app.services.preflight import as_dict, run_checks

router = APIRouter()


@router.get("/check")
def system_check(llm: bool = Query(False, description="Also test the connection to the LLM (slower)"),
                 _: Principal = Depends(require_role("ADMIN")), db: Session = Depends(get_db)):
    return as_dict(run_checks(db, check_llm=llm))


@router.get("/alerts")
def recent_alerts(limit: int = Query(25, ge=1, le=100), _: Principal = Depends(require_role("ADMIN")), db: Session = Depends(get_db)):
    """The latest problems that were (or should have been) announced, newest first."""
    from app.models.alert import AlertEvent
    rows = db.query(AlertEvent).order_by(AlertEvent.created_at.desc()).limit(limit).all()
    return [{"id": str(r.id), "kind": r.kind, "title": r.title, "body": r.body, "created_at": r.created_at.isoformat(),
             "delivered": r.delivered, "delivery": r.delivery, "attempts": r.attempts, "last_error": r.last_error,
             "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None} for r in rows]
