"""Validation for crawl sources added through the admin screen."""
from __future__ import annotations

import ipaddress
import socket
from typing import Optional
from urllib.parse import urlsplit

_BLOCKED_HOSTS = {"localhost", "localhost.localdomain", "metadata.google.internal"}


def _is_public(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    return not (addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_multicast
                or addr.is_reserved or addr.is_unspecified)


def validate_source_url(url: str, *, resolve: bool = True) -> str:
    """Return the domain of a safe public http(s) URL, else raise ValueError.

    The crawler fetches whatever URL is registered, so internal addresses (localhost, private
    networks, cloud metadata) are refused to keep a compromised account from probing the network.
    """
    parts = urlsplit((url or "").strip())
    if parts.scheme not in ("http", "https"):
        raise ValueError("The address must start with http:// or https://")
    if parts.username or parts.password:
        raise ValueError("Do not put a username or password in the address.")
    host = (parts.hostname or "").lower().rstrip(".")
    if not host or "." not in host and not _is_ip(host):
        raise ValueError("Enter a full website address, for example https://www.example.com/promo")
    if host in _BLOCKED_HOSTS or host.endswith((".local", ".internal", ".localhost")):
        raise ValueError("Internal addresses are not allowed.")
    if _is_ip(host):
        if not _is_public(host):
            raise ValueError("Private or internal IP addresses are not allowed.")
        return host
    if resolve:
        try:
            infos = socket.getaddrinfo(host, parts.port or (443 if parts.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
        except socket.gaierror:
            raise ValueError("This website address could not be found.") from None
        if not infos or not all(_is_public(i[4][0]) for i in infos):
            raise ValueError("This address points to a private or internal network and is not allowed.")
    return host


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def domain_matches(url_host: str, registered_domain: Optional[str]) -> bool:
    return bool(registered_domain) and (url_host == registered_domain or url_host.endswith("." + registered_domain))


def guard_request_url(url: str) -> None:
    """Refuse to fetch internal addresses (also applied to every redirect hop).

    A DNS failure is allowed through: the request itself will fail and be retried normally.
    """
    parts = urlsplit(str(url))
    host = (parts.hostname or "").lower().rstrip(".")
    if not host or host in _BLOCKED_HOSTS or host.endswith((".local", ".internal", ".localhost")):
        raise ValueError(f"Blocked internal address: {host or url}")
    if _is_ip(host):
        if not _is_public(host):
            raise ValueError(f"Blocked private address: {host}")
        return
    try:
        infos = socket.getaddrinfo(host, parts.port or (443 if parts.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return
    if any(not _is_public(i[4][0]) for i in infos):
        raise ValueError(f"Blocked: {host} resolves to a private address")
