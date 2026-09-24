import logging
from datetime import datetime, timezone
from typing import List

from sqlalchemy.orm import Session

from app.models.source import SourceRegistry, SourceUrl, CrawlDocument
from app.services.crawler.aggregator import AggregatorCrawler
from app.services.crawler.superindo import SuperindoCrawler
from app.services.crawler.base import BaseCrawler

logger = logging.getLogger(__name__)


def get_crawler_for_source(db: Session, source: SourceRegistry) -> BaseCrawler:
    adapter_key = (source.adapter_key or "").upper()
    if adapter_key == "SUPERINDO":
        return SuperindoCrawler(db, source)
    if adapter_key == "HEMAT":
        return AggregatorCrawler(db, source)
    raise ValueError(
        f"No approved source adapter for {source.name} ({source.domain}); "
        "source must not use a generic fallback"
    )


def run_all_crawlers(db: Session) -> List[CrawlDocument]:
    """Run only sources that currently have at least one due registered URL target."""
    now = datetime.now(timezone.utc)

    due_source_ids = {
        source_id
        for (source_id,) in (
            db.query(SourceUrl.source_id)
            .join(SourceRegistry, SourceRegistry.id == SourceUrl.source_id)
            .filter(
                SourceUrl.is_active.is_(True),
                (SourceUrl.next_crawl_at.is_(None)) | (SourceUrl.next_crawl_at <= now),
                SourceRegistry.is_active.is_(True),
                SourceRegistry.lifecycle_status == "ACTIVE",
                SourceRegistry.access_status.notin_(
                    ["BLOCKED", "LOGIN_REQUIRED", "CAPTCHA_REQUIRED", "PAYWALL"]
                ),
            )
            .distinct()
            .all()
        )
    }

    if not due_source_ids:
        logger.info("No approved active source URL targets are due for crawling.")
        return []

    sources = (
        db.query(SourceRegistry)
        .filter(SourceRegistry.id.in_(due_source_ids))
        .order_by(SourceRegistry.priority.asc(), SourceRegistry.name.asc())
        .all()
    )

    all_docs: List[CrawlDocument] = []
    for src in sources:
        try:
            logger.info(
                "Running registered crawler for due source: %s (%s)",
                src.name,
                src.domain,
            )
            crawler = get_crawler_for_source(db, src)
            docs = crawler.crawl()
            all_docs.extend(docs)
            src.last_yield_count = len(docs)
            logger.info("Source %s produced %s documents.", src.name, len(docs))
        except Exception as e:
            logger.error("Failed crawling source %s: %s", src.name, e)
            src.last_error_at = datetime.now(timezone.utc)
            db.commit()

    return all_docs
