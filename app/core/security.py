"""Authentication for privileged endpoints."""
import secrets
from typing import Optional

from fastapi import Header, HTTPException, status

from app.core.config import settings


def require_admin_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    """Guard endpoints that spend money (crawling, LLM calls).

    The endpoint is disabled entirely when ADMIN_API_KEY is not configured, so a
    fresh deployment is never accidentally open to the network.
    """
    configured = settings.ADMIN_API_KEY
    if not configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ADMIN_API_KEY is not configured on the server; this endpoint is disabled.",
        )
    if not x_api_key or not secrets.compare_digest(x_api_key.encode(), configured.encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid API key.",
        )
