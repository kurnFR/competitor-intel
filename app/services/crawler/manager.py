import logging
from datetime import datetime, timezone
from typing import List
from sqlalchemy.orm import Session
from app.models.source import SourceRegistry, CrawlDocument
from app.services.crawler.aggregator import AggregatorCrawler
from app.services.crawler.retailer import RetailerPromotionCrawler
from app.services.crawler.superindo import SuperindoCrawler
from app.services.crawler.base import BaseCrawler

logger = logging.getLogger(__name__)


def get_crawler_for_source(db: Session, source: SourceRegistry) -> BaseCrawler:
    domain = (source.domain or "").lower()
    if "superindo" in domain:
        return SuperindoCrawler(db, source)
    if "indomaret" in domain:
        return RetailerPromotionCrawler(db, source, "indomaret")
    if "alfamart" in domain:
        return RetailerPromotionCrawler(db, source, "alfamart")
    if "hemat.id" in domain or source.source_type == "PROMOTION_AGGREGATOR":
        return AggregatorCrawler(db, source)
    return AggregatorCrawler(db, source)


def run_all_crawlers(db: Session) -> List[CrawlDocument]:
    """Run active sources independently; one source failure must not stop the batch."""
    sources = db.query(SourceRegistry).filter(SourceRegistry.is_active == True).all()
    all_docs: List[CrawlDocument] = []

    for src in sources:
        crawler = None
        try:
            logger.info("Running crawler for source: %s (%s)", src.name, src.domain)
            crawler = get_crawler_for_source(db, src)
            docs = crawler.crawl()
            all_docs.extend(docs)
            logger.info("Source %s produced %s documents.", src.name, len(docs))
        except Exception as exc:
            logger.exception("Failed crawling source %s: %s", src.name, exc)
            db.rollback()
            # Re-fetch the source after rollback so this handler never relies on
            # potentially expired SQLAlchemy state from the failed transaction.
            fresh_src = db.get(SourceRegistry, src.id)
            if fresh_src is not None:
                fresh_src.last_error_at = datetime.now(timezone.utc)
                db.commit()
        finally:
            if crawler is not None:
                client = getattr(crawler, "client", None)
                close = getattr(client, "close", None)
                if callable(close):
                    close()

    return all_docs
