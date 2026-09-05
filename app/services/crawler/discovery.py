"""Bounded link discovery helpers for crawler adapters.

Discovery is deliberately conservative: same-origin links only, promotion-
relevant paths only, deterministic ordering, and a hard page budget. This
prevents a catalog crawler from turning into an unbounded site crawler.
"""

from __future__ import annotations

from typing import Iterable, List, Optional
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup


DEFAULT_MAX_PAGES = 10
PROMO_TERMS = (
    "promo", "promosi", "katalog", "hemat", "diskon", "sale", "deal",
    "biskuit", "kraker", "cracker", "wafer", "cookie", "snack",
)


def _same_origin(base_url: str, candidate: str) -> bool:
    base = urlparse(base_url)
    item = urlparse(candidate)
    return item.scheme in {"http", "https"} and item.netloc.lower() == base.netloc.lower()


def _is_relevant(candidate: str, base_url: str) -> bool:
    parsed = urlparse(candidate)
    haystack = f"{parsed.path}?{parsed.query}".lower()
    base_path = parsed.path.rstrip("/").lower()
    seed_path = urlparse(base_url).path.rstrip("/").lower()
    if seed_path and base_path.startswith(seed_path):
        return True
    return any(term in haystack for term in PROMO_TERMS)


def _strip_fragment(url: str) -> str:
    parsed = urlparse(url)
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", parsed.params, parsed.query, ""))


def _page_number(url: str) -> Optional[int]:
    for key, value in parse_qsl(urlparse(url).query, keep_blank_values=True):
        if key.lower() in {"page", "p", "paged", "page_num", "page_number"} and value.isdigit():
            return int(value)
    return None


def discover_pagination_urls(base_url: str, html: str, max_pages: int = DEFAULT_MAX_PAGES) -> List[str]:
    """Discover bounded, same-origin pagination URLs from one HTML page."""
    if max_pages < 1:
        return []
    soup = BeautifulSoup(html or "", "html.parser")
    discovered = {_strip_fragment(base_url)}

    for anchor in soup.select("a[href]"):
        href = anchor.get("href")
        if not href:
            continue
        candidate = _strip_fragment(urljoin(base_url, href))
        if not _same_origin(base_url, candidate) or not _is_relevant(candidate, base_url):
            continue
        rel = {str(x).lower() for x in (anchor.get("rel") or [])}
        text = anchor.get_text(" ", strip=True).lower()
        if _page_number(candidate) is not None or "next" in rel or "next" in text or "›" in text or "»" in text:
            discovered.add(candidate)

    numbered = sorted(discovered, key=lambda u: (_page_number(u) is None, _page_number(u) or 0, u))
    return numbered[:max_pages]


def merge_discovered_urls(seed_urls: Iterable[str], html_by_url: dict[str, str], max_pages: int = DEFAULT_MAX_PAGES) -> List[str]:
    """Expand seed URLs using pagination links without crossing source origins."""
    result: List[str] = []
    seen = set()
    for seed in seed_urls:
        canonical = _strip_fragment(seed)
        if canonical not in seen:
            seen.add(canonical)
            result.append(canonical)
        html = html_by_url.get(seed) or html_by_url.get(canonical) or ""
        for candidate in discover_pagination_urls(canonical, html, max_pages=max_pages):
            if candidate not in seen and len(result) < max_pages:
                seen.add(candidate)
                result.append(candidate)
    return result[:max_pages]
