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
def _fail_generic() -> AuthError:
    return AuthError("Invalid username or password.", 401, "INVALID_CREDENTIALS")


def _check_ip_and_lock(db: Session, username: str, ip: str) -> None:
    if ip_throttle.blocked(ip):
        audit(db, "login_throttled", username=username, success=False, ip=ip)
        db.commit()
        raise AuthError("Too many failed attempts. Try again later.", 429, "TOO_MANY_ATTEMPTS")


def _register_failure(db: Session, user: User, ip: str, reason: str) -> None:
    """Count a failed attempt (password or second factor) and lock the account when the limit is hit."""
    ip_throttle.record_failure(ip)
    if user.is_active:
        user.failed_login_count = (user.failed_login_count or 0) + 1
        if user.failed_login_count >= settings.LOGIN_MAX_FAILURES:
            user.locked_until = _now() + timedelta(minutes=settings.LOGIN_LOCK_MINUTES)
            user.failed_login_count = 0
            audit(db, "account_locked", username=user.username, success=False, ip=ip)
    audit(db, "login_failed", username=user.username, success=False, ip=ip, detail={"reason": reason})
    db.commit()


def verify_credentials(db: Session, username: str, password: str, *, ip: str) -> User:
    """Step 1: check username + password. Does NOT open a session (the caller decides, e.g. 2FA).

    Every failure returns the same generic message so usernames cannot be probed.
    """
    username = normalize_username(username)
    _check_ip_and_lock(db, username, ip)
    user = db.query(User).filter(func.lower(User.username) == username).first() if username else None
    now = _now()

    if user is None:
        verify_password(DUMMY_HASH, password or "")  # equalise timing
        ip_throttle.record_failure(ip)
        audit(db, "login_failed", username=username or None, success=False, ip=ip, detail={"reason": "unknown_user"})
        db.commit()
        raise _fail_generic()

    if user.locked_until and user.locked_until > now:
        verify_password(DUMMY_HASH, password or "")
        ip_throttle.record_failure(ip)
        audit(db, "login_blocked_locked", username=user.username, success=False, ip=ip)
        db.commit()
        raise AuthError("This account is temporarily locked. Try again later.", 423, "ACCOUNT_LOCKED")

    if not verify_password(user.password_hash, password or "") or not user.is_active:
        _register_failure(db, user, ip, "inactive" if not user.is_active else "bad_password")
        raise _fail_generic()

    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    return user


def complete_login(db: Session, user: User, *, ip: str, user_agent: str = "", method: str = "password") -> Tuple[str, UserSession]:
    """Final step: open the session. Returns (raw_cookie_token, session)."""
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = _now()
    ip_throttle.clear(ip)
    token, session = _open_session(db, user, ip=ip, user_agent=user_agent)
    audit(db, "login", username=user.username, ip=ip, detail={"method": method})
    db.commit()
    return token, session


def mfa_login(db: Session, challenge: str, code: str, *, ip: str, user_agent: str = "") -> Tuple[User, str, UserSession]:
    """Step 2 for accounts with 2FA: a valid challenge from step 1 plus an authenticator or recovery code."""
    from app.core import crypto
    from app.services import mfa

    bad = AuthError("The code is incorrect or expired. Sign in again if this keeps happening.", 401, "INVALID_MFA")
    user_id = crypto.verify_challenge(challenge or "")
    if user_id is None:
        ip_throttle.record_failure(ip)
        raise bad
    try:
        from uuid import UUID
        user = db.get(User, UUID(user_id))
    except ValueError:
        user = None
    if user is None or not user.is_active or not user.totp_enabled:
        raise bad
    _check_ip_and_lock(db, user.username, ip)
    now = _now()
    if user.locked_until and user.locked_until > now:
        audit(db, "login_blocked_locked", username=user.username, success=False, ip=ip)
        db.commit()
        raise AuthError("This account is temporarily locked. Try again later.", 423, "ACCOUNT_LOCKED")

    used_recovery = False
    if mfa.verify_totp(user, code):
        pass
    elif mfa.use_recovery_code(user, code):
        used_recovery = True
    else:
        _register_failure(db, user, ip, "bad_second_factor")
        raise bad
    token, session = complete_login(db, user, ip=ip, user_agent=user_agent,
                                    method="password+recovery_code" if used_recovery else "password+totp")
    if used_recovery:
        audit(db, "recovery_code_used", username=user.username, ip=ip,
              detail={"remaining": len(user.recovery_hashes or [])})
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
