import logging
from typing import List

from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.models.source import SourceRegistry, CrawlDocument
from app.services.crawler.base import BaseCrawler
from app.services.crawler.content import looks_dynamic_html, render_dynamic_page
from app.services.crawler.discovery import discover_pagination_urls

logger = logging.getLogger(__name__)

MAX_DISCOVERY_PAGES = 10
PROMO_KEYWORDS = ("rp", "diskon", "hemat", "beli", "promo", "gratis", "%")


class AggregatorCrawler(BaseCrawler):
    """Crawl promotion aggregators with bounded same-origin pagination discovery."""

    def _extract_promotion_text(self, html: str) -> tuple[str, int]:
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select(".item, .catalog-item, [class*='item']")
        extracted_lines = []
        for card in cards:
            txt = card.get_text(" ", strip=True)
            if any(keyword in txt.lower() for keyword in PROMO_KEYWORDS):
                clean_txt = " ".join(txt.split())
                if len(clean_txt) > 30 and clean_txt not in extracted_lines:
                    extracted_lines.append(clean_txt)

        text_content = "\n---\n".join(extracted_lines)
        if len(text_content) < 100:
            text_content, _ = self.extract_text(html)
        return text_content, len(extracted_lines)

    def crawl(self) -> List[CrawlDocument]:
        documents: List[CrawlDocument] = []
        seeds = [self.source.base_url]
        if "hemat.id" in (self.source.domain or "").lower():
            seeds.append("https://www.hemat.id/katalog/biskuit-kraker-wafer/?page=1")

        queue: List[str] = []
        seen = set()
        for seed in seeds:
            if seed and seed not in seen:
                seen.add(seed)
                queue.append(seed)

        index = 0
        while index < len(queue) and len(queue) <= MAX_DISCOVERY_PAGES:
            url = queue[index]
            index += 1
            logger.info("Crawling aggregator page %s/%s: %s", index, MAX_DISCOVERY_PAGES, url)

            status_code, html, error = self.fetch_url(url)
            if status_code != 200 or not html:
                self.record_crawl(url=url, http_status=status_code, raw_html="", text_content="", error_message=error)
                continue

            if looks_dynamic_html(html):
                rendered = render_dynamic_page(url)
                if rendered:
                    rendered_html, render_meta = rendered
                    html = rendered_html.decode("utf-8", errors="replace")
                else:
                    render_meta = {"dynamic_render_available": False}
            else:
                render_meta = {}

            text_content, item_count = self._extract_promotion_text(html)
            soup = BeautifulSoup(html, "html.parser")
            title = soup.title.get_text(strip=True) if soup.title else "Katalog Promo Biskuit & Kraker"
            metadata = {
                "total_items": item_count,
                "source_type": "AGGREGATOR",
                "discovery_page": index,
                **render_meta,
            }

            doc = self.record_crawl(
                url=url,
                http_status=status_code,
                raw_html=html,
                text_content=text_content,
                title=title,
                metadata=metadata,
            )
            if doc:
                documents.append(doc)

            if len(queue) < MAX_DISCOVERY_PAGES:
                for candidate in discover_pagination_urls(url, html, max_pages=MAX_DISCOVERY_PAGES):
                    if candidate not in seen and len(queue) < MAX_DISCOVERY_PAGES:
                        seen.add(candidate)
                        queue.append(candidate)

        return documents
