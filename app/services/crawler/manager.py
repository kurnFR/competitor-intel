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
        try:
            logger.info(f"Running crawler for source: {src.name} ({src.domain})")
            crawler = get_crawler_for_source(db, src)
            docs = crawler.crawl()
            all_docs.extend(docs)
            logger.info(f"Source {src.name} produced {len(docs)} documents.")
        except Exception as e:
            logger.error(f"Failed crawling source {src.name}: {e}")
    return all_docs
