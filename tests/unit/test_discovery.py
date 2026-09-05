from app.services.crawler.discovery import discover_pagination_urls, merge_discovered_urls


def test_discover_pagination_urls_keeps_same_origin_and_page_links():
    html = '''<html><body>
      <a href="/katalog/biskuit?page=2">2</a>
      <a href="/katalog/biskuit?page=3">3</a>
      <a href="https://other.example/promo?page=4">4</a>
      <a href="/about">About</a>
    </body></html>'''
    urls = discover_pagination_urls("https://example.com/katalog/biskuit?page=1", html, max_pages=10)
    assert urls == [
        "https://example.com/katalog/biskuit?page=1",
        "https://example.com/katalog/biskuit?page=2",
        "https://example.com/katalog/biskuit?page=3",
    ]


def test_discovery_is_bounded():
    links = "".join(f'<a href="/promo?page={i}">{i}</a>' for i in range(1, 30))
    urls = discover_pagination_urls("https://example.com/promo?page=1", links, max_pages=5)
    assert len(urls) == 5
    assert urls[0].endswith("page=1")
    assert urls[-1].endswith("page=4")


def test_merge_discovered_urls_deduplicates_seeds_and_links():
    seed = "https://example.com/promo?page=1"
    html = '<a href="/promo?page=2">Next</a><a href="/promo?page=1">1</a>'
    assert merge_discovered_urls([seed, seed], {seed: html}, max_pages=5) == [
        seed,
        "https://example.com/promo?page=2",
    ]
