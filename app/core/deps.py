"""FastAPI dependencies for authentication and authorisation."""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.auth import User, UserSession
from app.services import mfa as mfa_service
from app.services.auth import resolve_session, role_allows

SESSION_COOKIE = "ci_session"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@dataclass
class Principal:
    user: User
    session: UserSession


def client_ip(request: Request) -> str:
    if settings.TRUST_PROXY:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()[:45]
    return (request.client.host if request.client else "unknown")[:45]


def get_principal_optional(request: Request, db: Session = Depends(get_db)) -> Optional[Principal]:
    resolved = resolve_session(db, request.cookies.get(SESSION_COOKIE))
    return Principal(*resolved) if resolved else None


def _check_csrf(request: Request, principal: Principal) -> None:
    if request.method in UNSAFE_METHODS:
        sent = request.headers.get("x-csrf-token", "")
        if not sent or not secrets.compare_digest(sent.encode(), principal.session.csrf_token.encode()):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Missing or invalid CSRF token.")


def require_role(minimum: str = "VIEWER", *, allow_password_change_pending: bool = False):
    """Dependency factory: require a logged-in user with at least ``minimum`` role."""

    def dependency(request: Request, principal: Optional[Principal] = Depends(get_principal_optional)) -> Principal:
        if principal is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Login required.")
        if principal.user.must_change_password and not allow_password_change_pending:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "PASSWORD_CHANGE_REQUIRED")
        if mfa_service.setup_required(principal.user) and not allow_password_change_pending:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "MFA_SETUP_REQUIRED")
        if not role_allows(principal.user, minimum):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have permission for this action.")
        _check_csrf(request, principal)
        return principal

    return dependency


def require_admin_session_or_key(
    request: Request,
    x_api_key: Optional[str] = Header(default=None),
    principal: Optional[Principal] = Depends(get_principal_optional),
) -> Optional[Principal]:
    """Scan trigger: an ADMIN login session, or the automation key (no cookie involved)."""
    if x_api_key is not None:
        configured = settings.ADMIN_API_KEY
        if not configured:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "ADMIN_API_KEY is not configured on the server.")
        if not secrets.compare_digest(x_api_key.encode(), configured.encode()):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key.")
        return None
    return require_role("ADMIN")(request, principal)
