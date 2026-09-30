"""TOTP two-factor authentication: enrolment, verification, recovery codes."""
from __future__ import annotations

import re
import secrets
import time
from typing import List, Optional

import pyotp
import segno

from app.core import crypto
from app.core.config import settings
from app.models.auth import User

PERIOD = 30
RECOVERY_CODE_COUNT = 10


def available() -> bool:
    return crypto.secret_key_configured()


def setup_required(user: User) -> bool:
    return bool(available() and settings.MFA_REQUIRED_FOR_ADMINS and user.role == "ADMIN" and not user.totp_enabled)


def _normalize(code: str) -> str:
    return re.sub(r"[\s-]", "", (code or "")).lower()


def begin_enrollment(user: User) -> dict:
    """Create a new (not yet active) authenticator secret. Replaces any unfinished attempt."""
    secret = pyotp.random_base32()
    user.totp_secret_enc = crypto.encrypt(secret)
    user.totp_enabled = False
    user.totp_last_step = None
    uri = pyotp.TOTP(secret, interval=PERIOD).provisioning_uri(name=user.username, issuer_name=settings.APP_NAME)
    return {"secret": secret, "otpauth_uri": uri, "qr": segno.make(uri, error="m").svg_data_uri(scale=5, border=2)}


def _match_step(secret: str, code: str, last_step: Optional[int]) -> Optional[int]:
    """Return the time step the code belongs to (+-1 step tolerated), or None. Never a reused step."""
    code = _normalize(code)
    if not re.fullmatch(r"\d{6}", code):
        return None
    totp = pyotp.TOTP(secret, interval=PERIOD)
    now_step = int(time.time()) // PERIOD
    for step in (now_step, now_step - 1, now_step + 1):
        if secrets.compare_digest(totp.at(step * PERIOD), code):
            return step if (last_step is None or step > last_step) else None
    return None


def verify_totp(user: User, code: str) -> bool:
    """Check a code and remember its time step so the same code cannot be used twice."""
    if not user.totp_secret_enc:
        return False
    secret = crypto.decrypt(user.totp_secret_enc)
    if not secret:
        return False
    step = _match_step(secret, code, user.totp_last_step)
    if step is None:
        return False
    user.totp_last_step = step
    return True


def _new_recovery_codes() -> List[str]:
    return ["-".join(secrets.token_hex(2) for _ in range(3)) for _ in range(RECOVERY_CODE_COUNT)]


def confirm_enrollment(user: User, code: str) -> Optional[List[str]]:
    """Activate 2FA if the first code is right. Returns the recovery codes (shown once), else None."""
    if user.totp_enabled or not user.totp_secret_enc:
        return None
    if not verify_totp(user, code):
        return None
    codes = _new_recovery_codes()
    user.recovery_hashes = [crypto.hmac_hex("recovery", _normalize(c)) for c in codes]
    user.totp_enabled = True
    return codes


def use_recovery_code(user: User, code: str) -> bool:
    """Each recovery code works once."""
    wanted = crypto.hmac_hex("recovery", _normalize(code))
    hashes = list(user.recovery_hashes or [])
    for h in hashes:
        if secrets.compare_digest(h, wanted):
            hashes.remove(h)
            user.recovery_hashes = hashes
            return True
    return False


def check_second_factor(user: User, code: str) -> bool:
    return verify_totp(user, code) or use_recovery_code(user, code)


def disable(user: User) -> None:
    user.totp_enabled = False
    user.totp_secret_enc = None
    user.totp_last_step = None
    user.recovery_hashes = None
