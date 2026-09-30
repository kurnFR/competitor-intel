from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import SESSION_COOKIE, Principal, client_ip, get_principal_optional, require_role
from app.db.session import get_db
from app.models.auth import AuditLog, ROLES, User
from app.services import auth as auth_service
from app.services.auth import AuthError

router = APIRouter()


class LoginIn(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=256)


class UserOut(BaseModel):
    id: UUID
    username: str
    display_name: Optional[str] = None
    role: str
    is_active: bool
    must_change_password: bool
    locked: bool = False
    last_login_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class SessionOut(BaseModel):
    user: UserOut
    csrf_token: str


class ChangePasswordIn(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(max_length=256)


class NewUserIn(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=256, description="Temporary password; the user must change it at first login")
    role: str = "VIEWER"
    display_name: Optional[str] = Field(default=None, max_length=120)


class UpdateUserIn(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None
    display_name: Optional[str] = Field(default=None, max_length=120)


class ResetPasswordIn(BaseModel):
    new_password: str = Field(max_length=256)


class AuditOut(BaseModel):
    occurred_at: datetime
    username: Optional[str]
    action: str
    success: bool
    ip: Optional[str]
    detail: Optional[dict]

    model_config = {"from_attributes": True}


def _user_out(user: User) -> UserOut:
    out = UserOut.model_validate(user)
    out.locked = bool(user.locked_until and user.locked_until > datetime.now(user.locked_until.tzinfo))
    return out


def _fail(exc: AuthError):
    return HTTPException(status_code=exc.status_code, detail=exc.message)


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE, token, max_age=settings.SESSION_ABSOLUTE_HOURS * 3600, httponly=True,
        secure=settings.session_cookie_secure, samesite="strict", path="/",
    )


@router.post("/login", response_model=SessionOut)
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    try:
        user, token, session = auth_service.authenticate(
            db, body.username, body.password, ip=client_ip(request), user_agent=request.headers.get("user-agent", ""),
        )
    except AuthError as exc:
        raise _fail(exc)
    _set_cookie(response, token)
    response.headers["Cache-Control"] = "no-store"
    return SessionOut(user=_user_out(user), csrf_token=session.csrf_token)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response,
           principal: Principal = Depends(require_role("VIEWER", allow_password_change_pending=True)),
           db: Session = Depends(get_db)):
    auth_service.revoke_session(db, principal.session)
    auth_service.audit(db, "logout", username=principal.user.username, ip=client_ip(request))
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me", response_model=SessionOut)
def me(response: Response, principal: Optional[Principal] = Depends(get_principal_optional)):
    if principal is None:
        raise HTTPException(status_code=401, detail="Login required.")
    response.headers["Cache-Control"] = "no-store"
    return SessionOut(user=_user_out(principal.user), csrf_token=principal.session.csrf_token)


@router.post("/change-password", status_code=204)
def change_password(body: ChangePasswordIn, request: Request,
                    principal: Principal = Depends(require_role("VIEWER", allow_password_change_pending=True)),
                    db: Session = Depends(get_db)):
    user = principal.user
    if not auth_service.verify_password(user.password_hash, body.current_password):
        auth_service.audit(db, "password_change_failed", username=user.username, success=False, ip=client_ip(request))
        db.commit()
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    try:
        auth_service.set_password(db, user, body.new_password, keep_session_id=principal.session.id)
    except AuthError as exc:
        raise _fail(exc)
    auth_service.audit(db, "password_changed", username=user.username, ip=client_ip(request))
    db.commit()


# ---- administration --------------------------------------------------------
@router.get("/users", response_model=List[UserOut])
def list_users(_: Principal = Depends(require_role("ADMIN")), db: Session = Depends(get_db)):
    return [_user_out(u) for u in db.query(User).order_by(User.username).all()]


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: NewUserIn, request: Request, principal: Principal = Depends(require_role("ADMIN")),
                db: Session = Depends(get_db)):
    try:
        user = auth_service.create_user(db, username=body.username, password=body.password, role=body.role,
                                        display_name=body.display_name, must_change_password=True)
    except AuthError as exc:
        raise _fail(exc)
    auth_service.audit(db, "user_created", username=principal.user.username, ip=client_ip(request),
                       detail={"target": user.username, "role": user.role})
    db.commit()
    return _user_out(user)


def _target(db: Session, user_id: UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    return user


def _other_active_admins(db: Session, exclude_id) -> int:
    return db.query(User).filter(User.role == "ADMIN", User.is_active.is_(True), User.id != exclude_id).count()


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: UUID, body: UpdateUserIn, request: Request,
                principal: Principal = Depends(require_role("ADMIN")), db: Session = Depends(get_db)):
    user = _target(db, user_id)
    changes = {}
    if body.role is not None and body.role != user.role:
        if body.role not in ROLES:
            raise HTTPException(status_code=422, detail=f"Role must be one of {', '.join(ROLES)}.")
        if user.role == "ADMIN" and _other_active_admins(db, user.id) == 0:
            raise HTTPException(status_code=409, detail="There must be at least one active administrator.")
        changes["role"] = [user.role, body.role]
        user.role = body.role
    if body.is_active is not None and body.is_active != user.is_active:
        if not body.is_active:
            if user.id == principal.user.id:
                raise HTTPException(status_code=409, detail="You cannot deactivate your own account.")
            if user.role == "ADMIN" and _other_active_admins(db, user.id) == 0:
                raise HTTPException(status_code=409, detail="There must be at least one active administrator.")
            auth_service.revoke_user_sessions(db, user.id)
        changes["is_active"] = body.is_active
        user.is_active = body.is_active
    if body.role is not None and "role" in changes:
        auth_service.revoke_user_sessions(db, user.id, except_session_id=principal.session.id if user.id == principal.user.id else None)
    if body.display_name is not None:
        user.display_name = body.display_name
    auth_service.audit(db, "user_updated", username=principal.user.username, ip=client_ip(request),
                       detail={"target": user.username, **changes})
    db.commit()
    return _user_out(user)


@router.post("/users/{user_id}/reset-password", status_code=204)
def reset_password(user_id: UUID, body: ResetPasswordIn, request: Request,
                   principal: Principal = Depends(require_role("ADMIN")), db: Session = Depends(get_db)):
    user = _target(db, user_id)
    try:
        auth_service.set_password(db, user, body.new_password, must_change=True,
                                  keep_session_id=principal.session.id if user.id == principal.user.id else None)
    except AuthError as exc:
        raise _fail(exc)
    auth_service.audit(db, "password_reset", username=principal.user.username, ip=client_ip(request),
                       detail={"target": user.username})
    db.commit()


@router.post("/users/{user_id}/unlock", status_code=204)
def unlock_user(user_id: UUID, request: Request, principal: Principal = Depends(require_role("ADMIN")),
                db: Session = Depends(get_db)):
    user = _target(db, user_id)
    user.locked_until, user.failed_login_count = None, 0
    auth_service.audit(db, "user_unlocked", username=principal.user.username, ip=client_ip(request),
                       detail={"target": user.username})
    db.commit()


@router.get("/audit", response_model=List[AuditOut])
def audit_log(limit: int = 100, _: Principal = Depends(require_role("ADMIN")), db: Session = Depends(get_db)):
    limit = max(1, min(limit, 500))
    return db.query(AuditLog).order_by(AuditLog.occurred_at.desc()).limit(limit).all()
