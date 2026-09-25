import unittest
from types import SimpleNamespace
from unittest.mock import patch

import httpx

from app.services.crawler.base import BaseCrawler, canonicalize_url, compute_hash


class DummyCrawler(BaseCrawler):
    def crawl(self):
        return []


class FakeResponse:
    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text
        self.content = text.encode("utf-8")
        self.headers = {"content-type": "text/html; charset=utf-8"}


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def get(self, url):
        self.calls += 1
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def make_crawler(responses, max_retries):
    crawler = object.__new__(DummyCrawler)
    crawler.source = SimpleNamespace(id="test-source")
    crawler.max_retries = max_retries
    crawler.retry_backoff_seconds = 1
    crawler.client = FakeClient(responses)
    return crawler


def make_legacy_crawler(responses, max_retries):
    """Build the pre-source-context shape to verify fetch remains source-safe."""
    crawler = object.__new__(DummyCrawler)
    crawler.max_retries = max_retries
    crawler.retry_backoff_seconds = 1
    crawler.client = FakeClient(responses)
    return crawler


class CrawlerBaseTests(unittest.TestCase):
    def test_canonicalize_url_removes_fragment_and_normalizes_host(self):
        self.assertEqual(
            canonicalize_url("HTTPS://Example.COM/promo/?x=1#section"),
            "https://example.com/promo/?x=1",
        )

    def test_compute_hash_is_deterministic(self):
        self.assertEqual(compute_hash("promo"), compute_hash("promo"))
        self.assertNotEqual(compute_hash("promo"), compute_hash("promo-2"))

    def test_fetch_url_retries_transient_status_then_succeeds(self):
        crawler = make_crawler([FakeResponse(503), FakeResponse(200, "ok")], max_retries=2)

        with patch("app.services.crawler.base.time.sleep") as sleep:
            status, text, error = crawler.fetch_url("https://example.test/promo")

        self.assertEqual((status, text, error), (200, "ok", None))
        self.assertEqual(crawler.client.calls, 2)
        sleep.assert_called_once_with(1)

    def test_fetch_url_retries_http_error_then_returns_error(self):
        crawler = make_crawler([
            httpx.ConnectError("temporary connection failure"),
            httpx.ConnectError("temporary connection failure"),
        ], max_retries=1)

        with patch("app.services.crawler.base.time.sleep") as sleep:
            status, text, error = crawler.fetch_url("https://example.test/promo")

        self.assertEqual(status, 0)
        self.assertEqual(text, "")
        self.assertIn("temporary connection failure", error)
        self.assertEqual(crawler.client.calls, 2)
        sleep.assert_called_once_with(1)

    def test_fetch_url_does_not_retry_non_transient_status(self):
        crawler = make_crawler([FakeResponse(404, "missing")], max_retries=3)

        with patch("app.services.crawler.base.time.sleep") as sleep:
            status, text, error = crawler.fetch_url("https://example.test/missing")

        self.assertEqual((status, text, error), (404, "missing", None))
        self.assertEqual(crawler.client.calls, 1)
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
