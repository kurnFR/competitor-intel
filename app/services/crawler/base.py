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
from app.services.crawler.content import detect_document_type
from app.services.crawler.rate_limiter import RateLimitConfig, get_source_rate_limiter
from app.services.storage import get_raw_document_store

logger = logging.getLogger(__name__)
DEFAULT_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36", "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8", "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7"}
RETRYABLE_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}
INITIAL_RETRY_DELAY_SECONDS = 60
DEFAULT_MAX_RETRIES = 3
DEFAULT_REQUESTS_PER_SECOND = 1.0
DEFAULT_MAX_CONCURRENCY = 1


def compute_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def compute_bytes_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def canonicalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", parts.query, ""))


class BaseCrawler(ABC):
    def __init__(self, db: Session, source: SourceRegistry, max_retries: int = DEFAULT_MAX_RETRIES,
                 retry_backoff_seconds: float = 1.0, requests_per_second: float = DEFAULT_REQUESTS_PER_SECOND,
                 max_concurrency: int = DEFAULT_MAX_CONCURRENCY):
        self.db = db
        self.source = source
        self.max_retries = max(0, max_retries)
        self.retry_backoff_seconds = max(0.0, retry_backoff_seconds)
        self.rate_limit_config = RateLimitConfig(requests_per_second=requests_per_second, max_concurrency=max_concurrency)
        self.rate_limiter = get_source_rate_limiter()
        self.raw_store = get_raw_document_store()
        self.client = httpx.Client(headers=DEFAULT_HEADERS, timeout=30.0, follow_redirects=True, verify=True)

    def fetch_content(self, url: str) -> Tuple[int, bytes, str, Optional[str]]:
        last_status = 0
        last_error: Optional[str] = None
        source_key = str(self.source.id)
        for attempt in range(self.max_retries + 1):
            try:
                with self.rate_limiter.acquire(source_key, self.rate_limit_config):
                    resp = self.client.get(url)
                last_status = resp.status_code
                content_type = resp.headers.get("content-type", "")
                if resp.status_code not in RETRYABLE_STATUS_CODES:
                    return resp.status_code, resp.content, content_type, None
                last_error = f"HTTP {resp.status_code}"
            except httpx.HTTPError as exc:
                last_error = str(exc)
            if attempt < self.max_retries:
                delay = self.retry_backoff_seconds * (2 ** attempt)
                if delay:
                    time.sleep(delay)
        logger.error("Failed fetching %s after %s attempts: %s", url, self.max_retries + 1, last_error)
        return last_status, b"", "", last_error

    def fetch_url(self, url: str) -> Tuple[int, str, Optional[str]]:
        status, content, content_type, error = self.fetch_content(url)
        if error:
            return status, "", error
        document_type = detect_document_type(url, content_type, content)
        if document_type != "HTML":
            return status, "", f"NON_HTML_CONTENT:{document_type}"
        return status, content.decode("utf-8", errors="replace"), None

    def extract_text(self, html: str) -> Tuple[str, Optional[str]]:
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
        canonical_url = canonicalize_url(url)
        return self.db.query(CrawlDocument).filter(CrawlDocument.source_id == self.source.id,
            CrawlDocument.canonical_url == canonical_url, CrawlDocument.content_hash == content_hash).order_by(CrawlDocument.retrieved_at.desc()).first()

    def record_crawl_job(self, job: CrawlJob, http_status: int, raw_html: str, text_content: str,
                         title: Optional[str] = None, error_message: Optional[str] = None,
                         metadata: Optional[Dict[str, Any]] = None, raw_content: Optional[bytes] = None,
                         content_type: Optional[str] = None) -> Optional[CrawlDocument]:
        now = datetime.now(timezone.utc)
        canonical_url = canonicalize_url(job.url)
        raw_bytes = raw_content if raw_content is not None else (raw_html or "").encode("utf-8")
        content_hash = compute_hash(text_content or raw_html) if (text_content or raw_html) else None
        successful = 200 <= http_status < 400 and not error_message
        job.http_status = http_status
        job.content_hash = content_hash
        job.error_message = error_message
        job.completed_at = now if successful else None
        if successful and text_content:
            metadata = dict(metadata or {})
            detected_type = metadata.get("document_type") or detect_document_type(job.url, content_type or "", raw_bytes)
            extension = {"HTML": "html", "PDF": "pdf", "IMAGE": "img"}.get(detected_type, "bin")
            stored = self.raw_store.put(raw_bytes, content_type or "application/octet-stream", str(self.source.id), extension)
            metadata.update({"raw_storage_backend": "local", "raw_storage_sha256": stored.sha256, "raw_storage_size_bytes": stored.size_bytes})
            doc = self._existing_document(job.url, content_hash)
            if doc is None:
                doc = CrawlDocument(crawl_job_id=job.id, source_id=self.source.id, url=job.url,
                    canonical_url=canonical_url, document_type=detected_type, title=title,
                    raw_content_uri=stored.uri, text_content=text_content, content_hash=content_hash,
                    retrieved_at=now, http_status=http_status, metadata_json=metadata, created_at=now)
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

    def record_crawl(self, url: str, http_status: int, raw_html: str, text_content: str,
                     title: Optional[str] = None, error_message: Optional[str] = None,
                     metadata: Optional[Dict[str, Any]] = None) -> Optional[CrawlDocument]:
        now = datetime.now(timezone.utc)
        successful = 200 <= http_status < 400 and not error_message
        transient_failure = not successful and (http_status in RETRYABLE_STATUS_CODES or http_status == 0)
        if successful:
            status, retry_count, next_retry_at = "SUCCESS", 0, None
        elif transient_failure:
            status, retry_count, next_retry_at = "RETRY_WAIT", 1, now + timedelta(seconds=INITIAL_RETRY_DELAY_SECONDS)
        else:
            status, retry_count, next_retry_at = "DEAD_LETTER", 0, None
        job = CrawlJob(source_id=self.source.id, url=url, job_type="CATALOG", status=status,
            started_at=now, completed_at=now if successful or status == "DEAD_LETTER" else None,
            http_status=http_status, error_message=error_message, retry_count=retry_count,
            next_retry_at=next_retry_at, max_retries=DEFAULT_MAX_RETRIES, last_attempt_at=now, created_at=now)
        self.db.add(job)
        self.db.flush()
        doc = self.record_crawl_job(job, http_status, raw_html, text_content, title, error_message, metadata)
        self.db.commit()
        return doc

    @abstractmethod
    def crawl(self) -> List[CrawlDocument]:
        pass
