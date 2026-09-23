import logging
from typing import List
from sqlalchemy.orm import Session
from app.models.source import SourceRegistry, CrawlDocument
from app.services.crawler.aggregator import AggregatorCrawler
from app.services.crawler.superindo import SuperindoCrawler
from app.services.crawler.base import BaseCrawler

logger = logging.getLogger(__name__)


def get_crawler_for_source(db: Session, source: SourceRegistry) -> BaseCrawler:
    domain = (source.domain or "").lower()
    if "superindo" in domain:
        return SuperindoCrawler(db, source)
    if "hemat.id" in domain or source.source_type == "PROMOTION_AGGREGATOR":
        return AggregatorCrawler(db, source)
    raise ValueError(f"No approved source adapter for {source.name} ({source.domain}); source must not use a generic fallback")


def run_all_crawlers(db: Session) -> List[CrawlDocument]:
    sources = db.query(SourceRegistry).filter(
        SourceRegistry.is_active.is_(True),
        SourceRegistry.lifecycle_status == "ACTIVE",
        SourceRegistry.access_status.notin_(["BLOCKED", "LOGIN_REQUIRED", "CAPTCHA_REQUIRED", "PAYWALL"]),
    ).all()
    all_docs = []
    for src in sources:
        try:
            logger.info("Running registered crawler for source: %s (%s)", src.name, src.domain)
            crawler = get_crawler_for_source(db, src)
            docs = crawler.crawl()
            all_docs.extend(docs)
            logger.info("Source %s produced %s documents.", src.name, len(docs))
        except Exception as e:
            logger.error("Failed crawling source %s: %s", src.name, e)
            src.last_error_at = __import__('datetime').datetime.now(__import__('datetime').timezone.utc)
            db.commit()
    return all_docs
