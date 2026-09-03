import logging
from typing import List
from sqlalchemy.orm import Session
from app.models.source import SourceRegistry, CrawlDocument
from app.services.crawler.base import BaseCrawler

logger = logging.getLogger(__name__)


class SuperindoCrawler(BaseCrawler):
    """
    Crawls Superindo official promotion pages and flyers.
    """
    def crawl(self) -> List[CrawlDocument]:
        documents = []
        target_urls = [
            "https://www.superindo.co.id/promosi/katalog-super-hemat",
            "https://www.superindo.co.id/promosi/promo-koran"
        ]

        for url in target_urls:
            logger.info(f"Crawling Superindo URL: {url}")
            status_code, html, error = self.fetch_url(url)
            if status_code == 200 and html:
                text_content, title = self.extract_text(html)
                doc = self.record_crawl(
                    url=url,
                    http_status=status_code,
                    raw_html=html,
                    text_content=text_content,
                    title=title or "Superindo Promo Katalog",
                    metadata={"source": "Superindo Official"}
                )
                if doc:
                    documents.append(doc)
            else:
                self.record_crawl(
                    url=url,
                    http_status=status_code,
                    raw_html="",
                    text_content="",
                    error_message=error
                )

        return documents
