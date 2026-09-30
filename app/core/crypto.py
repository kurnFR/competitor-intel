"""Encryption and signing helpers derived from SECRET_KEY."""
from __future__ import annotations

import base64
import hashlib
import hmac
import time
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


class SecretKeyMissing(RuntimeError):
    pass


def _key(purpose: str) -> bytes:
    if not settings.SECRET_KEY or len(settings.SECRET_KEY) < 16:
        raise SecretKeyMissing("SECRET_KEY is not configured (at least 16 characters).")
    return hashlib.sha256(f"competitor-intel|{purpose}|{settings.SECRET_KEY}".encode()).digest()


def secret_key_configured() -> bool:
    return bool(settings.SECRET_KEY) and len(settings.SECRET_KEY) >= 16


def encrypt(plaintext: str) -> str:
    return Fernet(base64.urlsafe_b64encode(_key("fernet"))).encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> Optional[str]:
    try:
        return Fernet(base64.urlsafe_b64encode(_key("fernet"))).decrypt(token.encode()).decode()
    except InvalidToken:
        return None


def hmac_hex(purpose: str, value: str) -> str:
    return hmac.new(_key(purpose), value.encode(), hashlib.sha256).hexdigest()


def sign_challenge(user_id: str, ttl_seconds: int) -> str:
    expires = int(time.time()) + ttl_seconds
    payload = f"{user_id}.{expires}"
    return f"{payload}.{hmac_hex('mfa-challenge', payload)}"


def verify_challenge(token: str) -> Optional[str]:
    """Return the user id if the challenge is genuine and not expired."""
    try:
        user_id, expires, sig = token.rsplit(".", 2)
        payload = f"{user_id}.{expires}"
        if not hmac.compare_digest(sig, hmac_hex("mfa-challenge", payload)):
            return None
        return user_id if int(expires) >= time.time() else None
    except (ValueError, SecretKeyMissing):
        return None
