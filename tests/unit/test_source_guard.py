import pytest

from app.services.sources import guard_request_url, validate_source_url


@pytest.mark.parametrize("url", [
    "ftp://example.com/x", "javascript:alert(1)", "http://localhost/admin", "http://127.0.0.1:8000/",
    "http://10.0.0.5/", "http://192.168.1.10/", "http://169.254.169.254/latest/meta-data/",
    "http://[::1]/", "http://intranet/", "http://db.internal/", "https://user:pw@example.com/",
    "", "not a url",
])
def test_unsafe_source_urls_are_refused(url):
    with pytest.raises(ValueError):
        validate_source_url(url, resolve=False)


def test_public_ip_and_hostname_accepted_without_dns():
    assert validate_source_url("https://93.184.216.34/promo", resolve=False) == "93.184.216.34"
    assert validate_source_url("https://www.example.com/promo", resolve=False) == "www.example.com"


@pytest.mark.parametrize("url", [
    "http://169.254.169.254/latest/meta-data/", "http://127.0.0.1/", "http://10.1.2.3/", "http://localhost/",
    "http://[::1]/", "http://db.internal/",
])
def test_fetch_guard_blocks_internal_targets_including_redirect_hops(url):
    with pytest.raises(ValueError):
        guard_request_url(url)


def test_fetch_guard_allows_public_ip():
    guard_request_url("https://93.184.216.34/promo")


def test_http_client_blocks_a_redirect_to_an_internal_address():
    import httpx
    from app.services.crawler.base import _block_internal_requests

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "93.184.216.34":
            return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data/"})
        return httpx.Response(200, text="secret")

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True,
                          event_hooks={"request": [_block_internal_requests]})
    with pytest.raises(httpx.UnsupportedProtocol):
        client.get("https://93.184.216.34/promo")
