"""Crawler behaviour on saved pages, so layout changes are caught without touching the network."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.crawler.content import looks_dynamic_html
from app.services.crawler.retailer import RetailerPromotionCrawler

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


@pytest.fixture()
def crawler():
    source = SimpleNamespace(id="s1", domain="tokocontoh.example", base_url="https://tokocontoh.example/")
    return RetailerPromotionCrawler(None, source, "indomaret")


def test_discovers_only_relevant_same_site_promo_links(crawler):
    html = (FIXTURES / "retailer_home.html").read_text()
    urls = crawler.discover_promotion_urls(html, "https://tokocontoh.example/")
    assert "https://tokocontoh.example/promo/promo-mingguan" in urls
    assert all(u.startswith("https://tokocontoh.example/") for u in urls)   # no facebook/mailto/javascript
    assert not any("karir" in u for u in urls)
    assert len(urls) == len(set(urls))                                       # fragments/dups collapsed


def test_static_page_is_not_flagged_dynamic():
    assert not looks_dynamic_html((FIXTURES / "retailer_home.html").read_text())


def test_empty_js_shell_is_flagged_dynamic():
    shell = '<html><body><div id="__next"></div><script src="/_next/static/app.js"></script></body></html>'
    assert looks_dynamic_html(shell)
