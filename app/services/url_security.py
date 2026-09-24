from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse
from fastapi import HTTPException

def _reject_host(host: str, resolve_dns: bool = True) -> None:
    normalized = host.rstrip(".").lower()
    if normalized == "localhost" or normalized.endswith(".localhost"):
        raise HTTPException(status_code=422, detail="Localhost URLs are not allowed")
    try:
        literal = ipaddress.ip_address(normalized)
        addresses = {str(literal)}
    except ValueError:
        if not resolve_dns:
            return
        try:
            addresses = {info[4][0] for info in socket.getaddrinfo(normalized, None)}
        except socket.gaierror as exc:
            raise HTTPException(status_code=422, detail="URL hostname could not be resolved") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            raise HTTPException(status_code=422, detail="Private, local, reserved, or multicast URL targets are not allowed")

def validate_public_url(value: str, resolve_dns: bool = True) -> str:
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"}:
        raise HTTPException(status_code=422, detail="Only HTTP(S) URLs are allowed")
    if parsed.username or parsed.password:
        raise HTTPException(status_code=422, detail="URLs containing credentials are not allowed")
    if not parsed.hostname:
        raise HTTPException(status_code=422, detail="URL hostname is required")
    _reject_host(parsed.hostname, resolve_dns=resolve_dns)
    return parsed.geturl()
