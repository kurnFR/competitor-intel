"""Regression tests for the code-review fixes."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.schemas.ai import ExtractedPromotionItem
from app.services.channels import display_channel, normalize_channel, retailer_types_for
from app.services.crawler.base import BaseCrawler, ROBOTS_DISALLOWED, _robots_cache
from app.services.crawler.manager import get_crawler_for_source
from app.services.extraction.cards import split_into_cards
from app.services.ranking.scorer import PromotionScorer
from app.services.validation.validator import PromotionValidator


# --- card splitting -------------------------------------------------------
def test_cards_split_on_separator_and_report_total():
    text = "\n---\n".join(f"Card {i} " + "x" * 40 for i in range(50))
    cards, total = split_into_cards(text, max_cards=10)
    assert total == 50 and len(cards) == 10


def test_cards_fallback_splits_long_page_without_separators():
    text = "\n\n".join(f"Product {i} promo Rp{i}000 " + "y" * 200 for i in range(40))
    cards, total = split_into_cards(text, max_cards=300, fallback_chunk_chars=1000)
    assert total > 1
    assert "Product 39" in "\n".join(cards)  # nothing silently lost


def test_cards_empty():
    assert split_into_cards("  ", max_cards=5) == ([], 0)


# --- channels -------------------------------------------------------------
def test_channel_normalisation():
    assert normalize_channel("MINIMARKET") == "Modern Trade"
    assert normalize_channel("e-commerce") == "E-commerce"
    assert normalize_channel("nonsense") is None
    assert display_channel(None, "HYPERMARKET") == "Modern Trade"
    assert display_channel(None, None) == "N/A"
    assert "MINIMARKET" in retailer_types_for("Modern Trade")


# --- validator category ---------------------------------------------------
def _item(**kw):
    base = dict(product_name="Roma Kelapa 300g", brand="Roma", competitor="Mayora", pack_size="300g",
                promotion_type="DISCOUNT", promo_price=7000, discount_percentage=30, retailer="Indomaret",
                evidence_quote="Roma Kelapa 300g", confidence=0.9)
    base.update(kw)
    return ExtractedPromotionItem(**base)


def test_missing_category_is_not_guessed_as_biscuit():
    assert ExtractedPromotionItem(product_name="Something", promotion_type="DISCOUNT", evidence_quote="x").category == "OTHER"
    ok, reason, *_ = PromotionValidator.validate_and_normalize(_item(product_name="Detergen Rinso 1kg", brand="Rinso"))
    assert not ok and "outside core" in reason


def test_pie_keyword_is_whole_word_only():
    ok, *_ = PromotionValidator.validate_and_normalize(_item(product_name="Piece of cake mix", brand="X"))
    assert not ok
    ok, *_ = PromotionValidator.validate_and_normalize(_item(product_name="Apple Pie 200g", brand="X"))
    assert ok


# --- scoring --------------------------------------------------------------
def test_undated_promotions_rank_lower():
    now = datetime.now(timezone.utc)
    kw = dict(promotion_type="DISCOUNT", discount_percentage=30, source_reliability=0.9, last_seen_at=now,
              category="BISCUIT", competitor_importance=0.5, ai_confidence=0.9, now=now)
    dated = PromotionScorer.compute_total_score(**kw)
    undated = PromotionScorer.compute_total_score(**kw, dates_known=False)
    assert undated < dated


def test_freshness_decays_with_age():
    now = datetime.now(timezone.utc)
    assert PromotionScorer.calculate_freshness(now - timedelta(days=45), now=now) < \
        PromotionScorer.calculate_freshness(now, now=now)


# --- crawler --------------------------------------------------------------
@pytest.mark.parametrize("domain,expected", [("alfagift.id", "alfamart"), ("www.alfamart.co.id", "alfamart"),
                                              ("www.klikindomaret.com", "indomaret")])
def test_retailer_domain_maps_to_profile(domain, expected):
    source = SimpleNamespace(id="s1", domain=domain, base_url=f"https://{domain}", source_type="RETAILER")
    crawler = get_crawler_for_source(None, source)
    assert crawler.retailer_key == expected


class _Resp:
    def __init__(self, status, text=""):
        self.status_code, self.text = status, text


class _RobotsCrawler(BaseCrawler):
    def crawl(self):  # pragma: no cover
        return []


def test_robots_txt_is_honoured(monkeypatch):
    monkeypatch.setattr(settings, "CRAWLER_RESPECT_ROBOTS", True)
    _robots_cache.clear()
    crawler = _RobotsCrawler(None, SimpleNamespace(id="s1", domain="shop.test"))
    crawler.client = SimpleNamespace(get=lambda url: _Resp(200, "User-agent: *\nDisallow: /private\n"))
    assert crawler.robots_allows("https://shop.test/promo")
    assert not crawler.robots_allows("https://shop.test/private/x")
    status, body, _, error = crawler.fetch_content("https://shop.test/private/x")
    assert (status, body, error) == (403, b"", ROBOTS_DISALLOWED)


def test_missing_robots_txt_allows(monkeypatch):
    monkeypatch.setattr(settings, "CRAWLER_RESPECT_ROBOTS", True)
    _robots_cache.clear()
    crawler = _RobotsCrawler(None, SimpleNamespace(id="s1", domain="shop2.test"))
    crawler.client = SimpleNamespace(get=lambda url: _Resp(404))
    assert crawler.robots_allows("https://shop2.test/anything")


def test_crawler_identifies_itself_honestly():
    crawler = _RobotsCrawler(None, SimpleNamespace(id="s1", domain="shop.test"))
    assert "Mozilla" not in crawler.client.headers["User-Agent"]
