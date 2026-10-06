import logging
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List

from sqlalchemy.orm import Session

from app.models.source import CrawlDocument, SourceRegistry
from app.services.crawler.aggregator import AggregatorCrawler
from app.services.crawler.base import BaseCrawler
from app.services.crawler.retailer import RetailerPromotionCrawler
from app.services.crawler.superindo import SuperindoCrawler

logger = logging.getLogger(__name__)


class UnsupportedAdapter(ValueError):
    """The source has no usable adapter. It is reported as a failure, never crawled with a guessed parser."""


# adapter_key -> (factory, label shown in the admin screen)
ADAPTERS: Dict[str, Callable[[Session, SourceRegistry], BaseCrawler]] = {
    "superindo": lambda db, src: SuperindoCrawler(db, src),
    "indomaret": lambda db, src: RetailerPromotionCrawler(db, src, "indomaret"),
    "alfamart": lambda db, src: RetailerPromotionCrawler(db, src, "alfamart"),
    "generic_catalog": lambda db, src: AggregatorCrawler(db, src),
}
ADAPTER_LABELS = {
    "superindo": "Superindo (tuned)",
    "indomaret": "Indomaret / KlikIndomaret (tuned)",
    "alfamart": "Alfamart / Alfagift (tuned)",
    "generic_catalog": "Generic catalog reader (least reliable - verify the results)",
}


def get_crawler_for_source(db: Session, source: SourceRegistry) -> BaseCrawler:
    """Pick the crawler from the source's EXPLICIT adapter_key; domains are never sniffed."""
    factory = ADAPTERS.get(source.adapter_key or "")
    if factory is None:
        raise UnsupportedAdapter(f"Source '{source.name}' has no supported adapter (adapter_key={source.adapter_key!r}).")
    return factory(db, source)


def crawlable_sources(db: Session, *, only_due: bool = False, now: datetime | None = None) -> List[SourceRegistry]:
    """Approved, active sources with an adapter; optionally only those whose own schedule says they are due.

    Candidate / rejected / paused sources are never returned (PRD 6, 18).
    """
    now = now or datetime.now(timezone.utc)
    sources = (
        db.query(SourceRegistry)
        .filter(SourceRegistry.is_active.is_(True), SourceRegistry.approval_status == "APPROVED",
                SourceRegistry.adapter_key.isnot(None))
        .order_by(SourceRegistry.priority, SourceRegistry.name)
        .all()
    )
    if not only_due:
        return sources
    due = []
    for s in sources:
        interval = timedelta(minutes=s.crawl_frequency_minutes or 1440)
        if s.last_crawled_at is None or now - s.last_crawled_at >= interval:
            due.append(s)
    return due


def run_all_crawlers(db: Session, *, only_due: bool = False) -> List[CrawlDocument]:
    """Crawl approved sources independently; one source failure must not stop the batch.

    only_due=True (the scheduler) honours each source's own crawl frequency; "Scan now" crawls every approved source.
    """
    sources = crawlable_sources(db, only_due=only_due)
    logger.info("Crawling %d source(s)%s.", len(sources), " (due only)" if only_due else "")
    all_docs: List[CrawlDocument] = []

    for src in sources:
        crawler = None
        try:
            logger.info("Running crawler for source: %s (%s, adapter=%s)", src.name, src.domain, src.adapter_key)
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
                now = datetime.now(timezone.utc)
                fresh_src.last_error_at = now
                fresh_src.last_crawled_at = now      # an attempt was made; the failure shows on the source, not as "no promotions"
                db.commit()
        finally:
            if crawler is not None:
                client = getattr(crawler, "client", None)
                close = getattr(client, "close", None)
                if callable(close):
                    close()

    return all_docs
