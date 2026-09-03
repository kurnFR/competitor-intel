import logging
from typing import List
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
from app.models.source import SourceRegistry, CrawlDocument
from app.services.crawler.base import BaseCrawler

logger = logging.getLogger(__name__)


class AggregatorCrawler(BaseCrawler):
    """
    Crawls promotion aggregators like hemat.id for FMCG biscuits, wafers, and crackers.
    """
    def crawl(self) -> List[CrawlDocument]:
        documents = []
        target_urls = [
            self.source.base_url,
            "https://www.hemat.id/katalog/biskuit-kraker-wafer/?page=1",
            "https://www.hemat.id/katalog/biskuit-kraker-wafer/?page=2",
        ]

        for url in target_urls:
            logger.info(f"Crawling aggregator page: {url}")
            status_code, html, error = self.fetch_url(url)

            if status_code == 200 and html:
                soup = BeautifulSoup(html, "html.parser")
                title = soup.title.string.strip() if soup.title else "Katalog Promo Biskuit & Kraker"

                # Extract individual promotion card texts to retain clean context
                cards = soup.select(".item, .catalog-item, [class*='item']")
                extracted_lines = []
                for card in cards:
                    txt = card.get_text(" ", strip=True)
                    if any(k in txt.lower() for k in ["rp", "diskon", "hemat", "beli", "promo", "gratis", "%"]):
                        # Clean up multiple whitespaces
                        clean_txt = " ".join(txt.split())
                        if len(clean_txt) > 30 and clean_txt not in extracted_lines:
                            extracted_lines.append(clean_txt)

                text_content = "\n---\n".join(extracted_lines)
                if not text_content or len(text_content) < 100:
                    text_content, _ = self.extract_text(html)

                doc = self.record_crawl(
                    url=url,
                    http_status=status_code,
                    raw_html=html,
                    text_content=text_content,
                    title=title,
                    metadata={"total_items": len(extracted_lines), "source_type": "AGGREGATOR"}
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
