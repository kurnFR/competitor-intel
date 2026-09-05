from app.services.crawler.retailer import PROFILES, RetailerPromotionCrawler


def _crawler_for(key):
    crawler = RetailerPromotionCrawler.__new__(RetailerPromotionCrawler)
    crawler.retailer_key = key
    crawler.profile = PROFILES[key]
    crawler.source = type("Source", (), {"base_url": f"https://www.{key}.co.id/"})()
    return crawler


def test_indomaret_discovers_same_origin_promotion_links():
    crawler = _crawler_for("indomaret")
    html = """
    <a href="/promo/katalog-september">Katalog Promo</a>
    <a href="https://indomaret.co.id/promo/tebus-murah">Tebus Murah</a>
    <a href="https://example.com/promo">external promo</a>
    <a href="/tentang-kami">Tentang Kami</a>
    """
    urls = crawler.discover_promotion_urls(html, "https://www.indomaret.co.id/")
    assert urls == [
        "https://indomaret.co.id/promo/tebus-murah",
        "https://www.indomaret.co.id/promo/katalog-september",
    ]


def test_alfamart_matches_promo_and_catalog_keywords():
    crawler = _crawler_for("alfamart")
    html = """
    <a href="/promo-jsm">JSM</a>
    <a href="/katalog">Katalog</a>
    <a href="/karir">Karir</a>
    """
    urls = crawler.discover_promotion_urls(html, "https://www.alfamart.co.id/")
    assert urls == [
        "https://www.alfamart.co.id/katalog",
        "https://www.alfamart.co.id/promo-jsm",
    ]


def test_retailer_profile_rejects_unknown_retailer():
    try:
        RetailerPromotionCrawler(None, type("Source", (), {})(), "unknown")
    except ValueError as exc:
        assert "Unsupported retailer profile" in str(exc)
    else:
        raise AssertionError("Expected unsupported retailer profile to fail")
