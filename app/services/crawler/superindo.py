import logging
from typing import List
from sqlalchemy.orm import Session
from app.models.source import SourceRegistry, SourceUrl, CrawlDocument
from app.services.crawler.base import BaseCrawler

logger = logging.getLogger(__name__)


class SuperindoCrawler(BaseCrawler):
    """Crawls only approved URL targets registered for the Superindo source."""
    def crawl(self) -> List[CrawlDocument]:
        documents = []
        urls = self.db.query(SourceUrl).filter(
            SourceUrl.source_id == self.source.id,
            SourceUrl.is_active.is_(True),
        ).order_by(SourceUrl.priority.asc(), SourceUrl.next_crawl_at.asc().nullsfirst()).all()

        for target in urls:
            if target.next_crawl_at and target.next_crawl_at > __import__('datetime').datetime.now(__import__('datetime').timezone.utc):
                continue
            logger.info("Crawling registered Superindo URL: %s", target.url)
            status_code, html, error = self.fetch_url(target.url)
            if status_code == 200 and html:
                text_content, title = self.extract_text(html)
                doc = self.record_crawl(target.url, status_code, html, text_content, title=title or "Superindo Promo", metadata={"source": "Superindo Official"}, source_url_id=target.id)
                if doc:
                    documents.append(doc)
            else:
                self.record_crawl(target.url, status_code, "", "", error_message=error, source_url_id=target.id)
        return documents
