from app.services.crawler.content import detect_document_type, looks_dynamic_html


def test_detect_pdf_from_magic_bytes():
    assert detect_document_type("https://example.com/catalog", "", b"%PDF-1.7") == "PDF"


def test_detect_image_from_mime():
    assert detect_document_type("https://example.com/catalog", "image/png", b"x") == "IMAGE"


def test_detect_html_from_mime():
    assert detect_document_type("https://example.com/catalog", "text/html", b"x") == "HTML"


def test_detect_pdf_from_extension():
    assert detect_document_type("https://example.com/catalog.PDF") == "PDF"


def test_dynamic_html_heuristic():
    html = '<html><body><div id="__next"></div><script src="webpack.js"></script></body></html>'
    assert looks_dynamic_html(html)


def test_normal_html_not_marked_dynamic():
    html = '<html><body>' + ('promotion details ' * 100) + '</body></html>'
    assert not looks_dynamic_html(html)
