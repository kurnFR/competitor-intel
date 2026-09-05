"""Bridge durable CrawlJob records to source adapters and content acquisition."""

from typing import Optional, Tuple

from app.models.source import CrawlJob
from app.services.crawler.base import RETRYABLE_STATUS_CODES, compute_hash, compute_bytes_hash
from app.services.crawler.content import detect_document_type, extract_non_html, looks_dynamic_html, render_dynamic_page
from app.services.crawler.job_errors import PermanentCrawlJobError
from app.services.crawler.manager import get_crawler_for_source


class CrawlJobProcessor:
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
            status_code, content, content_type, error = crawler.fetch_content(job.url)
            if error:
                if status_code in RETRYABLE_STATUS_CODES or status_code == 0:
                    raise RuntimeError(error)
                raise PermanentCrawlJobError(error)
            if not (200 <= status_code < 400):
                raise PermanentCrawlJobError(f"HTTP {status_code} for {job.url}")
            if not content:
                raise RuntimeError(f"Empty response body for {job.url}")

            document_type = detect_document_type(job.url, content_type, content)
            metadata = {"worker_reprocessed": True, "source_type": source.source_type,
                        "content_type": content_type, "document_type": document_type}

            if document_type == "HTML":
                html = content.decode("utf-8", errors="replace")
                text_content, title = crawler.extract_text(html)
                if looks_dynamic_html(html) or len(text_content.strip()) < 50:
                    rendered = render_dynamic_page(job.url)
                    if rendered:
                        html_bytes, render_meta = rendered
                        html = html_bytes.decode("utf-8", errors="replace")
                        text_content, title = crawler.extract_text(html)
                        content = html_bytes
                        metadata.update(render_meta)
                    else:
                        metadata["dynamic_render_available"] = False
                if not text_content or len(text_content.strip()) < 50:
                    raise RuntimeError(f"Insufficient extracted text for {job.url}")
                raw_content = html
            elif document_type in {"PDF", "IMAGE"}:
                acquired = extract_non_html(job.url, content_type, content)
                metadata.update(acquired.metadata)
                if acquired.error:
                    raise RuntimeError(acquired.error)
                text_content = acquired.text
                title = None
                raw_content = content.decode("latin-1")
                if not text_content or len(text_content.strip()) < 20:
                    raise RuntimeError(f"No usable text extracted from {document_type} source {job.url}")
            else:
                raise PermanentCrawlJobError(f"Unsupported content type for {job.url}: {content_type or 'unknown'}")

            content_hash = compute_hash(text_content) if text_content else compute_bytes_hash(content)
            crawler.record_crawl_job(job=job, http_status=status_code, raw_html=raw_content,
                text_content=text_content, title=title, metadata=metadata, raw_content=content,
                content_type=content_type)
            return status_code, content_hash
        finally:
            client = getattr(crawler, "client", None)
            close = getattr(client, "close", None)
            if callable(close):
                close()
