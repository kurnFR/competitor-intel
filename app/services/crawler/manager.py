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
    elif "hemat.id" in domain or source.source_type == "PROMOTION_AGGREGATOR":
        return AggregatorCrawler(db, source)
    else:
        return AggregatorCrawler(db, source)


def run_all_crawlers(db: Session) -> List[CrawlDocument]:
    sources = db.query(SourceRegistry).filter(SourceRegistry.is_active == True).all()
    all_docs = []

    for src in sources:
        crawler = None
        try:
            logger.info("Running crawler for source: %s (%s)", src.name, src.domain)
            crawler = get_crawler_for_source(db, src)
            docs = crawler.crawl()
            all_docs.extend(docs)
            logger.info("Source %s produced %s documents.", src.name, len(docs))
        except Exception as exc:
            # One broken source must not prevent the remaining sources from running.
            logger.exception("Failed crawling source %s: %s", src.name, exc)
            db.rollback()
            src.last_error_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
            db.commit()
        finally:
            if crawler is not None:
                client = getattr(crawler, "client", None)
                close = getattr(client, "close", None)
                if callable(close):
                    close()

    return all_docs
