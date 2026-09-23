import logging
from typing import List
from sqlalchemy.orm import Session
from bs4 import BeautifulSoup
from app.models.source import SourceRegistry, SourceUrl, CrawlDocument
from app.services.crawler.base import BaseCrawler

logger = logging.getLogger(__name__)


class AggregatorCrawler(BaseCrawler):
    """Crawls only approved URL targets registered for the source."""
    def crawl(self) -> List[CrawlDocument]:
        documents = []
        urls = self.db.query(SourceUrl).filter(
            SourceUrl.source_id == self.source.id,
            SourceUrl.is_active.is_(True),
        ).order_by(SourceUrl.priority.asc(), SourceUrl.next_crawl_at.asc().nullsfirst()).all()
        if not urls:
            logger.warning("No registered URLs for source %s; refusing to invent crawl targets", self.source.name)
            return documents

        for target in urls:
            if target.next_crawl_at and target.next_crawl_at > __import__('datetime').datetime.now(__import__('datetime').timezone.utc):
                continue
            status_code, html, error = self.fetch_url(target.url)
            if status_code == 200 and html:
                soup = BeautifulSoup(html, "html.parser")
                title = soup.title.string.strip() if soup.title and soup.title.string else "Promotion page"
                cards = soup.select(".item, .catalog-item, [class*='item']")
                extracted_lines = []
                for card in cards:
                    txt = " ".join(card.get_text(" ", strip=True).split())
                    if any(k in txt.lower() for k in ["rp", "diskon", "hemat", "beli", "promo", "gratis", "%"]):
                        if len(txt) > 30 and txt not in extracted_lines:
                            extracted_lines.append(txt)
                text_content = "\n---\n".join(extracted_lines)
                if not text_content or len(text_content) < 100:
                    text_content, _ = self.extract_text(html)
                doc = self.record_crawl(target.url, status_code, html, text_content, title=title, metadata={"total_items": len(extracted_lines), "source_type": self.source.source_type}, source_url_id=target.id)
                if doc:
                    documents.append(doc)
            else:
                self.record_crawl(target.url, status_code, "", "", error_message=error, source_url_id=target.id)
        return documents
