from unittest.mock import MagicMock, patch

import pytest

from app.services.crawler.superindo import SuperindoCrawler


def _make_crawler():
    crawler = SuperindoCrawler.__new__(SuperindoCrawler)
    crawler.retailer_key = "superindo"
    crawler.max_pages = 10
    crawler.source = type("Source", (), {"id": "src-superindo-1", "base_url": "https://www.superindo.co.id/promosi/katalog-super-hemat"})()
    crawler.db = MagicMock()
    return crawler


def test_superindo_discover_promotion_urls():
    crawler = _make_crawler()
    html = """
    <div>
        <a href="/promosi/promo-koran">Promo Koran Mingguan</a>
        <a href="/promosi/diskon-spesial-biskuit">Diskon Biskuit</a>
        <a href="https://other.com/promosi">External</a>
        <a href="/karir">Karir Superindo</a>
        <img src="/assets/promo-super-hemat-banner.jpg" alt="Katalog Super Hemat" />
        <img src="/assets/logo.png" alt="Superindo Logo" />
    </div>
    """
    urls = crawler.discover_promotion_urls(html, "https://www.superindo.co.id/")
    assert "https://www.superindo.co.id/promosi/promo-koran" in urls
    assert "https://www.superindo.co.id/promosi/diskon-spesial-biskuit" in urls
    assert "https://www.superindo.co.id/assets/promo-super-hemat-banner.jpg" in urls
    assert not any("other.com" in u for u in urls)
    assert not any("karir" in u for u in urls)
    assert not any("logo.png" in u for u in urls)


def test_superindo_crawler_handles_errors_gracefully():
    crawler = _make_crawler()
    crawler.fetch_content = MagicMock(return_value=(503, b"", "", "Service Unavailable"))
    crawler._record_html = MagicMock(return_value=([], ""))

    docs = crawler.crawl()
    assert docs == []
    assert crawler.fetch_content.called
    assert crawler._record_html.called


def test_superindo_crawler_crawls_html_and_asset():
    crawler = _make_crawler()

    html_content = b"<html><head><title>Superindo Promo</title></head><body><h1>Promo Super Hemat</h1><p>Biskuit Roma Kelapa Rp 7.500 diskon 20%</p></body></html>"
    image_content = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00"

    def mock_fetch(url):
        if "promo-koran" in url:
            return 200, image_content, "image/jpeg", None
        return 200, html_content, "text/html", None

    crawler.fetch_content = MagicMock(side_effect=mock_fetch)
    crawler.max_pages = 2

    mock_doc = MagicMock()
    crawler.record_crawl = MagicMock(return_value=mock_doc)

    docs = crawler.crawl()
    assert len(docs) >= 1
    assert crawler.record_crawl.called
