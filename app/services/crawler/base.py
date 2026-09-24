import hashlib
import logging
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple, List
import httpx
from bs4 import BeautifulSoup
import trafilatura
from sqlalchemy.orm import Session
from app.models.source import SourceRegistry, SourceUrl, CrawlJob, CrawlDocument

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
}


def compute_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class BaseCrawler(ABC):
    def __init__(self, db: Session, source: SourceRegistry):
        self.db = db
        self.source = source
        self.client = httpx.Client(
            headers=DEFAULT_HEADERS,
            timeout=30.0,
            follow_redirects=True,
            verify=False
        )

    def fetch_url(self, url: str) -> Tuple[int, str, Optional[str]]:
        """Fetch a public URL using HTTP or an approved browser-rendered mode."""
        try:
            if self.source.access_mode == "BROWSER":
                from playwright.sync_api import sync_playwright
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(headless=True)
                    page = browser.new_page(extra_http_headers=DEFAULT_HEADERS)
                    response = page.goto(url, wait_until="networkidle", timeout=60000)
                    html = page.content()
                    status = response.status if response else 200
                    browser.close()
                    return status, html, None
            resp = self.client.get(url)
            return resp.status_code, resp.text, None
        except Exception as e:
            logger.error(f"Error fetching %s: %s", url, e)
            return 0, "", str(e)

    def extract_text(self, html: str) -> Tuple[str, Optional[str]]:
        """
        Extracts clean readable text and page title.
        """
        if not html:
            return "", None

        # Trafilatura extracts clean article/catalog content without nav/footer boilerplate
        extracted = trafilatura.extract(html, include_tables=True, include_links=True)
        
        soup = BeautifulSoup(html, "html.parser")
        title_tag = soup.find("title")
        title = title_tag.get_text().strip() if title_tag else None

        if not extracted or len(extracted.strip()) < 50:
            # Fallback to BeautifulSoup if trafilatura stripped too much
            extracted = soup.get_text(separator="\n", strip=True)

        return extracted or "", title

    def record_crawl(
        self,
        url: str,
        http_status: int,
        raw_html: str,
        text_content: str,
        title: Optional[str] = None,
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        source_url_id: Optional[uuid.UUID] = None
    ) -> Optional[CrawlDocument]:
        """
        Creates CrawlJob and CrawlDocument records in database.
        """
        now = datetime.now(timezone.utc)
        content_hash = compute_hash(text_content or raw_html) if (text_content or raw_html) else None

        unchanged = False
        target = None
        if source_url_id:
            target = self.db.query(SourceUrl).filter(SourceUrl.id == source_url_id).first()
            unchanged = bool(http_status == 200 and not error_message and content_hash and target and target.last_content_hash == content_hash)

        job_status = "UNCHANGED" if unchanged else ("SUCCESS" if (http_status == 200 and not error_message) else "FAILED")
        job = CrawlJob(
            source_id=self.source.id,
            source_url_id=source_url_id,
            url=url,
            job_type="CATALOG",
            status=job_status,
            started_at=now,
            completed_at=now,
            http_status=http_status,
            error_message=error_message,
            content_hash=content_hash,
            created_at=now
        )
        self.db.add(job)
        self.db.flush()

        doc = None
        if http_status == 200 and text_content and not unchanged:
            doc = CrawlDocument(
                crawl_job_id=job.id,
                source_id=self.source.id,
                url=url,
                document_type="HTML",
                title=title,
                text_content=text_content,
                content_hash=content_hash,
                retrieved_at=now,
                http_status=http_status,
                metadata_json=metadata or {},
                created_at=now
            )
            self.db.add(doc)

            # Update source stats
            self.source.last_crawled_at = now
            self.source.last_success_at = now
            self.source.consecutive_failures = 0
            if target:
                    target.last_crawled_at = now
                    target.last_changed_at = now if target.last_content_hash != content_hash else target.last_changed_at
                    target.last_content_hash = content_hash
                    target.consecutive_failures = 0
                    target.last_http_status = http_status
                    from datetime import timedelta
                    target.next_crawl_at = now + timedelta(minutes=max(1, target.frequency_minutes))
            self.db.flush()
        elif unchanged:
            self.source.last_crawled_at = now
            self.source.last_success_at = now
            self.source.consecutive_failures = 0
            if target:
                target.last_crawled_at = now
                target.last_http_status = http_status
                from datetime import timedelta
                target.next_crawl_at = now + timedelta(minutes=max(1, target.frequency_minutes))
        else:
            self.source.last_crawled_at = now
            self.source.last_error_at = now
            self.source.consecutive_failures += 1
            if target:
                    target.consecutive_failures += 1
                    target.last_http_status = http_status
                    from datetime import timedelta
                    backoff = min(1440, max(15, target.frequency_minutes * (2 ** min(target.consecutive_failures, 5))))
                    target.next_crawl_at = now + timedelta(minutes=backoff)

        self.db.commit()
        return doc

    @abstractmethod
    def crawl(self) -> List[CrawlDocument]:
        """Execute the crawl operation for this source."""
        pass
