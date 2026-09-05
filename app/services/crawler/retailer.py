"""Retailer-specific discovery for major Indonesian FMCG promotion sources.

The adapter deliberately discovers links from the configured retailer landing page
instead of hard-coding fragile product URLs. It only follows same-origin links that
look like promotion, catalog, flyer, or sale pages, plus direct PDF/image assets.
"""

from __future__ import annotations

import logging
from typing import List, Set
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.models.source import CrawlDocument, SourceRegistry
from app.services.crawler.base import BaseCrawler, canonicalize_url
from app.services.crawler.content import detect_document_type, extract_non_html, looks_dynamic_html, render_dynamic_page

logger = logging.getLogger(__name__)


PROFILES = {
    "indomaret": {
        "keywords": ("promo", "promosi", "catalog", "katalog", "hemat", "jsm", "tebus"),
    },
    "alfamart": {
        "keywords": ("promo", "promosi", "katalog", "catalog", "jsm", "serba", "tebus"),
    },
}


class RetailerPromotionCrawler(BaseCrawler):
    """Source-specific promotion discovery for supported retailer domains."""

    def __init__(self, db: Session, source: SourceRegistry, retailer_key: str):
        super().__init__(db, source)
        key = retailer_key.lower().strip()
        if key not in PROFILES:
            raise ValueError(f"Unsupported retailer profile: {retailer_key}")
        self.retailer_key = key
        self.profile = PROFILES[key]
        self.max_pages = 10

    def _is_relevant_link(self, href: str, text: str) -> bool:
        parsed = urlparse(href)
        source_host = urlparse(self.source.base_url).netloc.lower()
        if parsed.netloc and parsed.netloc.lower() != source_host:
            return False
        haystack = f"{parsed.path} {parsed.query} {text}".lower()
        return any(keyword in haystack for keyword in self.profile["keywords"])

    def discover_promotion_urls(self, html: str, base_url: str) -> List[str]:
        soup = BeautifulSoup(html, "html.parser")
        found: Set[str] = set()
        for anchor in soup.find_all("a", href=True):
            href = urljoin(base_url, anchor["href"])
            if self._is_relevant_link(href, anchor.get_text(" ", strip=True)):
                found.add(canonicalize_url(href))
        return sorted(found)

    def _record_html(self, url: str, status: int, html: str, metadata: dict) -> List[CrawlDocument]:
        if status != 200 or not html:
            self.record_crawl(url, status, "", "", error_message=metadata.get("error"), metadata=metadata)
            return []
        if looks_dynamic_html(html):
            rendered = render_dynamic_page(url)
            if rendered:
                rendered_html, render_meta = rendered
                html = rendered_html.decode("utf-8", errors="replace")
                metadata.update(render_meta)
        text, title = self.extract_text(html)
        if not text.strip():
            self.record_crawl(url, status, html, "", error_message="EMPTY_EXTRACTED_TEXT", metadata=metadata)
            return []
        doc = self.record_crawl(url, status, html, text, title=title, metadata=metadata)
        return [doc] if doc else []

    def _record_asset(self, url: str, status: int, content: bytes, content_type: str) -> List[CrawlDocument]:
        if status != 200 or not content:
            self.record_crawl(url, status, "", "", error_message=f"HTTP_{status}", metadata={"asset": True})
            return []
        acquired = extract_non_html(url, content_type, content)
        if acquired.error or not acquired.text.strip():
            self.record_crawl(url, status, "", "", error_message=acquired.error or "EMPTY_ASSET_TEXT",
                               metadata={"asset": True, "document_type": acquired.document_type, **acquired.metadata})
            return []
        doc = self.record_crawl(url, status, "", acquired.text, title=acquired.title,
                                metadata={"asset": True, "document_type": acquired.document_type, **acquired.metadata})
        return [doc] if doc else []

    def crawl(self) -> List[CrawlDocument]:
        documents: List[CrawlDocument] = []
        queue = [self.source.base_url]
        seen: Set[str] = set()

        while queue and len(seen) < self.max_pages:
            url = canonicalize_url(queue.pop(0))
            if url in seen:
                continue
            seen.add(url)
            status, content, content_type, error = self.fetch_content(url)
            if error:
                documents.extend(self._record_html(url, status, "", {"retailer": self.retailer_key, "error": error}))
                continue

            document_type = detect_document_type(url, content_type, content)
            if document_type == "HTML":
                html = content.decode("utf-8", errors="replace")
                documents.extend(self._record_html(url, status, html, {
                    "retailer": self.retailer_key,
                    "adapter": "retailer_promotion",
                    "discovery_page": len(seen),
                }))
                for discovered in self.discover_promotion_urls(html, url):
                    if discovered not in seen and len(seen) + len(queue) < self.max_pages:
                        queue.append(discovered)
            elif document_type in {"PDF", "IMAGE"}:
                documents.extend(self._record_asset(url, status, content, content_type))
            else:
                logger.info("Ignoring unsupported content from %s", url)

        return documents
