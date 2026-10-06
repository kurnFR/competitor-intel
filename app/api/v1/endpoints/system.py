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
