"""Password hashing (Argon2id) and strength rules."""
from __future__ import annotations

from typing import List

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import settings

_hasher = PasswordHasher()  # Argon2id with library defaults

# Tiny blocklist of the most common choices; length is the main defence.
_COMMON = {
    "password", "password1", "password123", "passw0rd", "123456789012", "qwertyuiop12", "qwerty123456",
    "iloveyou1234", "administrator", "welcome12345", "letmein12345", "changeme1234", "admin1234567",
    "competitor", "competitorintel", "indomaret123", "alfamart123", "abc123456789", "111111111111",
}


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(stored_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(stored_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(stored_hash)
    except InvalidHashError:
        return True


# A valid hash of a random value, used to spend the same time when the user does not exist.
DUMMY_HASH = _hasher.hash("not-a-real-password-\u2603")


def password_problems(password: str, username: str = "") -> List[str]:
    problems: List[str] = []
    min_len = settings.PASSWORD_MIN_LENGTH
    if len(password) < min_len:
        problems.append(f"Use at least {min_len} characters.")
    if len(password) > 256:
        problems.append("Use at most 256 characters.")
    lowered = password.lower()
    if lowered in _COMMON or lowered.strip("0123456789") in _COMMON:
        problems.append("This password is too common.")
    if username and username.lower() in lowered:
        problems.append("Do not include your username.")
    if len(set(password)) < 5:
        problems.append("Use a more varied password.")
    return problems
