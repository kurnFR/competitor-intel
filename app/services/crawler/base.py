import hashlib
import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Tuple, List
from urllib.parse import urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup
import trafilatura
from sqlalchemy.orm import Session

from app.models.source import SourceRegistry, CrawlJob, CrawlDocument
from app.services.crawler.rate_limiter import RateLimitConfig, get_source_rate_limiter

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
}

RETRYABLE_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}
INITIAL_RETRY_DELAY_SECONDS = 60
DEFAULT_MAX_RETRIES = 3
DEFAULT_REQUESTS_PER_SECOND = 1.0
DEFAULT_MAX_CONCURRENCY = 1


def compute_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def canonicalize_url(url: str) -> str:
    """Normalize a URL enough to make crawl-document identity deterministic."""
    parts = urlsplit(url.strip())
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", parts.query, ""))


class BaseCrawler(ABC):
    def __init__(
        self,
        db: Session,
        source: SourceRegistry,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_backoff_seconds: float = 1.0,
        requests_per_second: float = DEFAULT_REQUESTS_PER_SECOND,
        max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
    ):
        self.db = db
        self.source = source
        self.max_retries = max(0, max_retries)
        self.retry_backoff_seconds = max(0.0, retry_backoff_seconds)
        self.rate_limit_config = RateLimitConfig(
            requests_per_second=requests_per_second,
            max_concurrency=max_concurrency,
        )
        self.rate_limiter = get_source_rate_limiter()
        self.client = httpx.Client(
            headers=DEFAULT_HEADERS,
            timeout=30.0,
            follow_redirects=True,
            verify=True,
        )

    def fetch_url(self, url: str) -> Tuple[int, str, Optional[str]]:
        """Fetch URL with source-level pacing and bounded transient retries."""
        last_status = 0
        last_error: Optional[str] = None
        source_key = str(self.source.id)

        for attempt in range(self.max_retries + 1):
            try:
                with self.rate_limiter.acquire(source_key, self.rate_limit_config):
                    resp = self.client.get(url)
                last_status = resp.status_code

                if resp.status_code not in RETRYABLE_STATUS_CODES:
                    return resp.status_code, resp.text, None

                last_error = f"HTTP {resp.status_code}"
                logger.warning(
                    "Transient HTTP failure for %s (attempt %s/%s): %s",
                    url,
                    attempt + 1,
                    self.max_retries + 1,
                    last_error,
                )
            except httpx.HTTPError as exc:
                last_error = str(exc)
                logger.warning(
                    "Error fetching %s (attempt %s/%s): %s",
                    url,
                    attempt + 1,
                    self.max_retries + 1,
                    exc,
                )

            if attempt < self.max_retries:
                delay = self.retry_backoff_seconds * (2 ** attempt)
                if delay:
                    time.sleep(delay)

        logger.error("Failed fetching %s after %s attempts: %s", url, self.max_retries + 1, last_error)
        return last_status, "", last_error

    def extract_text(self, html: str) -> Tuple[str, Optional[str]]:
        """Extract clean readable text and page title."""
        if not html:
            return "", None

        extracted = trafilatura.extract(html, include_tables=True, include_links=True)
        soup = BeautifulSoup(html, "html.parser")
        title_tag = soup.find("title")
        title = title_tag.get_text().strip() if title_tag else None

        if not extracted or len(extracted.strip()) < 50:
            extracted = soup.get_text(separator="\n", strip=True)

        return extracted or "", title

    def _existing_document(self, url: str, content_hash: Optional[str]) -> Optional[CrawlDocument]:
        """Find an existing successful document with the same source, URL and content hash."""
        canonical_url = canonicalize_url(url)
        query = self.db.query(CrawlDocument).filter(
            CrawlDocument.source_id == self.source.id,
            CrawlDocument.canonical_url == canonical_url,
            CrawlDocument.content_hash == content_hash,
        )
        return query.order_by(CrawlDocument.retrieved_at.desc()).first()

    def record_crawl_job(
        self,
        job: CrawlJob,
        http_status: int,
        raw_html: str,
        text_content: str,
        title: Optional[str] = None,
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[CrawlDocument]:
        """Persist a result against an existing CrawlJob without creating another job."""
        now = datetime.now(timezone.utc)
        canonical_url = canonicalize_url(job.url)
        content_hash = compute_hash(text_content or raw_html) if (text_content or raw_html) else None
        successful = 200 <= http_status < 400 and not error_message

        job.http_status = http_status
        job.content_hash = content_hash
        job.error_message = error_message
        job.completed_at = now if successful else None

        doc = None
        if successful and text_content:
            doc = self._existing_document(job.url, content_hash)
            if doc is None:
                doc = CrawlDocument(
                    crawl_job_id=job.id,
                    source_id=self.source.id,
                    url=job.url,
                    canonical_url=canonical_url,
                    document_type="HTML",
                    title=title,
                    text_content=text_content,
                    content_hash=content_hash,
                    retrieved_at=now,
                    http_status=http_status,
                    metadata_json=metadata or {},
                    created_at=now,
                )
                self.db.add(doc)
                self.db.flush()
            else:
                logger.info("Skipping duplicate crawl document for %s (content_hash=%s)", canonical_url, content_hash)

            self.source.last_crawled_at = now
            self.source.last_success_at = now
            return doc

        self.source.last_crawled_at = now
        self.source.last_error_at = now
        return None

    def record_crawl(
        self,
        url: str,
        http_status: int,
        raw_html: str,
        text_content: str,
        title: Optional[str] = None,
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[CrawlDocument]:
        """Record a new crawl job and persist only new document content."""
        now = datetime.now(timezone.utc)
        successful = 200 <= http_status < 400 and not error_message
        transient_failure = not successful and (
            http_status in RETRYABLE_STATUS_CODES or http_status == 0
        )
        if successful:
            status = "SUCCESS"
            retry_count = 0
            next_retry_at = None
        elif transient_failure:
            status = "RETRY_WAIT"
            retry_count = 1
            next_retry_at = now + timedelta(seconds=INITIAL_RETRY_DELAY_SECONDS)
        else:
            status = "DEAD_LETTER"
            retry_count = 0
            next_retry_at = None

        job = CrawlJob(
            source_id=self.source.id,
            url=url,
            job_type="CATALOG",
            status=status,
            started_at=now,
            completed_at=now if successful or status == "DEAD_LETTER" else None,
            http_status=http_status,
            error_message=error_message,
            retry_count=retry_count,
            next_retry_at=next_retry_at,
            max_retries=DEFAULT_MAX_RETRIES,
            last_attempt_at=now,
            created_at=now,
        )
        self.db.add(job)
        self.db.flush()

        doc = self.record_crawl_job(
            job=job,
            http_status=http_status,
            raw_html=raw_html,
            text_content=text_content,
            title=title,
            error_message=error_message,
            metadata=metadata,
        )
        self.db.commit()
        return doc

    @abstractmethod
    def crawl(self) -> List[CrawlDocument]:
        """Execute the crawl operation for this source."""
        pass
