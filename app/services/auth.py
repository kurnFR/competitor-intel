"""Login, sessions, lockout and audit logging."""
from __future__ import annotations

import hashlib
import logging
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Deque, Dict, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.passwords import DUMMY_HASH, hash_password, needs_rehash, password_problems, verify_password
from app.models.auth import AuditLog, ROLES, User, UserSession

logger = logging.getLogger(__name__)

ROLE_RANK = {"VIEWER": 1, "ANALYST": 2, "ADMIN": 3}
SESSION_TOUCH_INTERVAL = timedelta(minutes=1)


class AuthError(Exception):
    def __init__(self, message: str, status_code: int = 401, code: str = "AUTH_FAILED"):
        super().__init__(message)
        self.message, self.status_code, self.code = message, status_code, code


def _now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_username(username: str) -> str:
    return (username or "").strip().lower()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ---- audit ---------------------------------------------------------------
def audit(db: Session, action: str, *, username: Optional[str] = None, success: bool = True,
          ip: Optional[str] = None, detail: Optional[dict] = None) -> None:
    db.add(AuditLog(username=username, action=action, success=success, ip=ip, detail=detail))
    logger.info("AUDIT action=%s user=%s success=%s ip=%s", action, username, success, ip)


# ---- per-IP failure throttle (in-memory; the app runs as a single process) --
class _IpThrottle:
    def __init__(self) -> None:
        self._events: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, q: Deque[float], now: float) -> None:
        window = settings.LOGIN_IP_WINDOW_MINUTES * 60
        while q and now - q[0] > window:
            q.popleft()

    def blocked(self, ip: str) -> bool:
        now = time.monotonic()
        with self._lock:
            q = self._events[ip]
            self._prune(q, now)
            return len(q) >= settings.LOGIN_IP_MAX_FAILURES

    def record_failure(self, ip: str) -> None:
        now = time.monotonic()
        with self._lock:
            q = self._events[ip]
            self._prune(q, now)
            q.append(now)

    def clear(self, ip: Optional[str] = None) -> None:
        with self._lock:
            if ip is None:
                self._events.clear()
            else:
                self._events.pop(ip, None)


ip_throttle = _IpThrottle()


# ---- users ---------------------------------------------------------------
def create_user(db: Session, *, username: str, password: str, role: str = "VIEWER",
                display_name: Optional[str] = None, must_change_password: bool = False) -> User:
    username = normalize_username(username)
    if not username or len(username) > 64 or not all(c.isalnum() or c in "._-@" for c in username):
        raise AuthError("Username may only contain letters, digits and . _ - @ (max 64).", 422, "INVALID_USERNAME")
    if role not in ROLES:
        raise AuthError(f"Role must be one of {', '.join(ROLES)}.", 422, "INVALID_ROLE")
    problems = password_problems(password, username)
    if problems:
        raise AuthError(" ".join(problems), 422, "WEAK_PASSWORD")
    if db.query(User).filter(func.lower(User.username) == username).first():
        raise AuthError("That username already exists.", 409, "USERNAME_TAKEN")
    user = User(username=username, display_name=display_name, password_hash=hash_password(password),
                role=role, must_change_password=must_change_password)
    db.add(user)
    db.flush()
    return user


def set_password(db: Session, user: User, new_password: str, *, must_change: bool = False,
                 keep_session_id=None) -> None:
    problems = password_problems(new_password, user.username)
    if problems:
        raise AuthError(" ".join(problems), 422, "WEAK_PASSWORD")
    if verify_password(user.password_hash, new_password):
        raise AuthError("The new password must be different from the current one.", 422, "PASSWORD_REUSED")
    user.password_hash = hash_password(new_password)
    user.password_changed_at = _now()
    user.must_change_password = must_change
    user.failed_login_count = 0
    user.locked_until = None
    revoke_user_sessions(db, user.id, except_session_id=keep_session_id)


# ---- login ---------------------------------------------------------------
def authenticate(db: Session, username: str, password: str, *, ip: str, user_agent: str = "") -> Tuple[User, str, UserSession]:
    """Verify credentials and open a session. Returns (user, raw_cookie_token, session).

    Every failure returns the same generic message so usernames cannot be probed.
    """
    username = normalize_username(username)
    generic = AuthError("Invalid username or password.", 401, "INVALID_CREDENTIALS")

    if ip_throttle.blocked(ip):
        audit(db, "login_throttled", username=username, success=False, ip=ip)
        db.commit()
        raise AuthError("Too many failed attempts. Try again later.", 429, "TOO_MANY_ATTEMPTS")

    user = db.query(User).filter(func.lower(User.username) == username).first() if username else None
    now = _now()

    if user is None:
        verify_password(DUMMY_HASH, password or "")  # equalise timing
        ip_throttle.record_failure(ip)
        audit(db, "login_failed", username=username or None, success=False, ip=ip, detail={"reason": "unknown_user"})
        db.commit()
        raise generic

    if user.locked_until and user.locked_until > now:
        verify_password(DUMMY_HASH, password or "")
        ip_throttle.record_failure(ip)
        audit(db, "login_blocked_locked", username=user.username, success=False, ip=ip)
        db.commit()
        raise AuthError("This account is temporarily locked. Try again later.", 423, "ACCOUNT_LOCKED")

    if not verify_password(user.password_hash, password or "") or not user.is_active:
        ip_throttle.record_failure(ip)
        reason = "inactive" if not user.is_active else "bad_password"
        if user.is_active:
            user.failed_login_count = (user.failed_login_count or 0) + 1
            if user.failed_login_count >= settings.LOGIN_MAX_FAILURES:
                user.locked_until = now + timedelta(minutes=settings.LOGIN_LOCK_MINUTES)
                user.failed_login_count = 0
                audit(db, "account_locked", username=user.username, success=False, ip=ip)
        audit(db, "login_failed", username=user.username, success=False, ip=ip, detail={"reason": reason})
        db.commit()
        raise generic

    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    ip_throttle.clear(ip)
    token, session = _open_session(db, user, ip=ip, user_agent=user_agent)
    audit(db, "login", username=user.username, ip=ip)
    db.commit()
    return user, token, session


def _open_session(db: Session, user: User, *, ip: str, user_agent: str) -> Tuple[str, UserSession]:
    token = secrets.token_urlsafe(48)
    now = _now()
    session = UserSession(
        user_id=user.id, token_hash=_hash_token(token), csrf_token=secrets.token_urlsafe(32),
        created_at=now, last_seen_at=now, expires_at=now + timedelta(hours=settings.SESSION_ABSOLUTE_HOURS),
        ip=ip[:45] if ip else None, user_agent=(user_agent or "")[:255],
    )
    db.add(session)
    db.flush()
    return token, session


# ---- sessions ------------------------------------------------------------
def resolve_session(db: Session, token: Optional[str]) -> Optional[Tuple[User, UserSession]]:
    """Return (user, session) for a valid cookie token, else None."""
    if not token:
        return None
    session = db.query(UserSession).filter(UserSession.token_hash == _hash_token(token)).first()
    if session is None or session.revoked_at is not None:
        return None
    now = _now()
    if session.expires_at <= now or now - session.last_seen_at > timedelta(minutes=settings.SESSION_IDLE_MINUTES):
        return None
    user = session.user
    if user is None or not user.is_active:
        return None
    if now - session.last_seen_at > SESSION_TOUCH_INTERVAL:
        session.last_seen_at = now
        db.commit()
    return user, session


def revoke_session(db: Session, session: UserSession) -> None:
    session.revoked_at = _now()


def revoke_user_sessions(db: Session, user_id, *, except_session_id=None) -> int:
    q = db.query(UserSession).filter(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
    if except_session_id is not None:
        q = q.filter(UserSession.id != except_session_id)
    return q.update({"revoked_at": _now()}, synchronize_session=False)


def purge_expired_sessions(db: Session) -> int:
    cutoff = _now() - timedelta(days=7)
    n = db.query(UserSession).filter((UserSession.expires_at < cutoff) | (UserSession.revoked_at < cutoff)).delete(synchronize_session=False)
    db.commit()
    return n


def role_allows(user: User, minimum: str) -> bool:
    return ROLE_RANK.get(user.role, 0) >= ROLE_RANK[minimum]
