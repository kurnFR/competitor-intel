"""Superindo official promotion pages and multimodal flyer catalog crawler."""
from __future__ import annotations

import logging
from typing import List, Set, Tuple
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.models.source import CrawlDocument, SourceRegistry
from app.services.crawler.base import BaseCrawler, canonicalize_url
from app.services.crawler.content import (
    detect_document_type,
    extract_non_html,
    looks_dynamic_html,
    render_dynamic_page,
)

logger = logging.getLogger(__name__)

SUPERINDO_PROMO_KEYWORDS = (
    "promo", "promosi", "katalog", "catalog", "koran", "super-hemat",
    "hemat", "diskon", "jsm", "biskuit", "snack",
)

DEFAULT_SUPERINDO_URLS = [
    "https://www.superindo.co.id/promosi/katalog-super-hemat",
    "https://www.superindo.co.id/promosi/promo-koran",
]


def _host_without_www(host: str) -> str:
    return host.lower().removeprefix("www.")


class SuperindoCrawler(BaseCrawler):
    """Crawls Superindo official promotion pages, dynamic catalogs, and flyer assets."""

    def __init__(self, db: Session, source: SourceRegistry):
        super().__init__(db, source)
        self.retailer_key = "superindo"
        self.max_pages = 10

    def _is_relevant_link(self, href: str, text: str) -> bool:
        parsed = urlparse(href)
        source_host = _host_without_www(urlparse(self.source.base_url or "https://www.superindo.co.id").netloc)
        candidate_host = _host_without_www(parsed.netloc) if parsed.netloc else source_host
        if candidate_host != source_host:
            return False
        haystack = f"{parsed.path} {parsed.query} {text}".lower()
        return any(keyword in haystack for keyword in SUPERINDO_PROMO_KEYWORDS)

    def discover_promotion_urls(self, html: str, base_url: str) -> List[str]:
        soup = BeautifulSoup(html, "html.parser")
        found: Set[str] = set()

        for anchor in soup.find_all("a", href=True):
            href = urljoin(base_url, anchor["href"])
            img_text = " ".join(filter(None, [img.get("alt") or img.get("title") for img in anchor.find_all("img")]))
            combined_text = f"{anchor.get_text(' ', strip=True)} {img_text}".strip()
            if self._is_relevant_link(href, combined_text):
                found.add(canonicalize_url(href))

        # Also discover flyer image URLs directly visible on the promo page
        for img in soup.find_all("img", src=True):
            src = urljoin(base_url, img["src"])
            img_text = f"{img.get('alt', '')} {img.get('title', '')}".strip()
            if self._is_relevant_link(src, img_text):
                found.add(canonicalize_url(src))

        return sorted(found)

    def _record_html(self, url: str, status: int, html: str, metadata: dict) -> Tuple[List[CrawlDocument], str]:
        if status != 200 or not html:
            self.record_crawl(url, status, "", "", error_message=metadata.get("error") or f"HTTP_{status}", metadata=metadata)
            return [], html

        if looks_dynamic_html(html):
            rendered = render_dynamic_page(url)
            if rendered:
                rendered_html, render_meta = rendered
                html = rendered_html.decode("utf-8", errors="replace")
                metadata.update(render_meta)

        text, title = self.extract_text(html)
        if not text.strip():
            self.record_crawl(
                url, status, html, "",
                error_message="EMPTY_EXTRACTED_TEXT",
                metadata=metadata,
                raw_content=html.encode("utf-8"),
                content_type="text/html",
            )
            return [], html

        doc = self.record_crawl(
            url, status, html, text,
            title=title or "Superindo Promo Katalog",
            metadata=metadata,
            raw_content=html.encode("utf-8"),
            content_type="text/html",
        )
        return ([doc] if doc else []), html

    def _record_asset(self, url: str, status: int, content: bytes, content_type: str) -> List[CrawlDocument]:
        if status != 200 or not content:
            self.record_crawl(url, status, "", "", error_message=f"HTTP_{status}", metadata={"asset": True, "retailer": "superindo"})
            return []

        acquired = extract_non_html(url, content_type, content)
        if acquired.error or not acquired.text.strip():
            # Still record flyer images even with empty OCR so FlyerVisionExtractor can inspect them via vision LLM
            meta = {
                "asset": True,
                "document_type": acquired.document_type,
                "retailer": "superindo",
                "source": "Superindo Official",
                **acquired.metadata,
            }
            # Provide placeholder text if OCR returned empty so document is persisted
            fallback_text = acquired.text.strip() or f"Superindo Promotional Flyer Asset: {url}"
            doc = self.record_crawl(
                url, status, "", fallback_text,
                title=acquired.title or "Superindo Flyer Catalog",
                metadata=meta,
                raw_content=content,
                content_type=content_type,
            )
            return [doc] if doc else []

        doc = self.record_crawl(
            url, status, "", acquired.text,
            title=acquired.title or "Superindo Flyer Catalog",
            metadata={"asset": True, "document_type": acquired.document_type, "retailer": "superindo", "source": "Superindo Official", **acquired.metadata},
            raw_content=content,
            content_type=content_type,
        )
        return [doc] if doc else []

    def crawl(self) -> List[CrawlDocument]:
        documents: List[CrawlDocument] = []
        queue: List[str] = []

        # Start with source base_url if set, and default Superindo promo URLs
        base_url = (self.source.base_url or "").strip()
        if base_url:
            queue.append(base_url)

        for u in DEFAULT_SUPERINDO_URLS:
            if u not in queue:
                queue.append(u)

        seen: Set[str] = set()

        while queue and len(seen) < self.max_pages:
            raw_url = queue.pop(0)
            url = canonicalize_url(raw_url)
            if url in seen:
                continue
            seen.add(url)

            logger.info("Crawling Superindo URL: %s", url)
            status, content, content_type, error = self.fetch_content(url)
            if error:
                logger.warning("Superindo fetch failed for %s: %s (status=%s)", url, error, status)
                self._record_html(url, status, "", {"retailer": "superindo", "source": "Superindo Official", "error": error})
                continue

            document_type = detect_document_type(url, content_type, content)
            if document_type == "HTML":
                html = content.decode("utf-8", errors="replace")
                meta = {
                    "source": "Superindo Official",
                    "retailer": "superindo",
                    "adapter": "superindo",
                    "discovery_page": len(seen),
                }
                new_docs, discovery_html = self._record_html(url, status, html, meta)
                documents.extend(new_docs)

                # Discover further promotion links and flyer assets from the page
                for discovered in self.discover_promotion_urls(discovery_html, url):
                    if discovered not in seen and len(seen) + len(queue) < self.max_pages:
                        queue.append(discovered)

            elif document_type in {"PDF", "IMAGE"}:
                new_docs = self._record_asset(url, status, content, content_type)
                documents.extend(new_docs)
            else:
                logger.info("Ignoring unsupported Superindo content from %s (type=%s)", url, document_type)

        logger.info("Superindo crawl completed: %d documents collected across %d pages", len(documents), len(seen))
        return documents
