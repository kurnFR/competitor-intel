"""Bridge durable CrawlJob records to existing source crawler adapters."""

from typing import Optional, Tuple

from app.models.source import CrawlJob
from app.services.crawler.base import RETRYABLE_STATUS_CODES, compute_hash
from app.services.crawler.job_errors import PermanentCrawlJobError
from app.services.crawler.manager import get_crawler_for_source


class CrawlJobProcessor:
    """Process one persisted CrawlJob using the configured source crawler."""

    def __init__(self, db):
        self.db = db

    def __call__(self, job: CrawlJob) -> Tuple[Optional[int], Optional[str]]:
        source = job.source
        if source is None:
            raise PermanentCrawlJobError(f"Source not found for crawl job {job.id}")
        if not source.is_active:
            raise PermanentCrawlJobError(f"Source is inactive: {source.name}")
        if not source.robots_allowed:
            raise PermanentCrawlJobError(f"Robots policy disallows crawling source: {source.name}")

        crawler = get_crawler_for_source(self.db, source)
        try:
            status_code, html, error = crawler.fetch_url(job.url)

            if error:
                if status_code in RETRYABLE_STATUS_CODES or status_code == 0:
                    raise RuntimeError(error)
                raise PermanentCrawlJobError(error)

            if not (200 <= status_code < 400):
                raise PermanentCrawlJobError(f"HTTP {status_code} for {job.url}")

            if not html:
                raise RuntimeError(f"Empty response body for {job.url}")

            text_content, title = crawler.extract_text(html)
            if not text_content or len(text_content.strip()) < 50:
                raise RuntimeError(f"Insufficient extracted text for {job.url}")

            content_hash = compute_hash(text_content or html)
            crawler.record_crawl_job(
                job=job,
                http_status=status_code,
                raw_html=html,
                text_content=text_content,
                title=title,
                metadata={"worker_reprocessed": True, "source_type": source.source_type},
            )
            return status_code, content_hash
        finally:
            client = getattr(crawler, "client", None)
            close = getattr(client, "close", None)
            if callable(close):
                close()
