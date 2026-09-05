"""Content acquisition and extraction helpers for non-HTML and dynamic sources.

Optional capabilities are deliberately soft-fail: the crawler can still process
ordinary HTML when PDF/OCR/browser dependencies are not installed.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse


@dataclass
class AcquiredContent:
    status_code: int
    content: bytes
    content_type: str
    document_type: str
    text: str = ""
    title: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


def detect_document_type(url: str, content_type: str = "", content: bytes = b"") -> str:
    """Return HTML, PDF, IMAGE, or UNKNOWN using headers, extension and magic bytes."""
    mime = (content_type or "").split(";", 1)[0].strip().lower()
    path = urlparse(url).path.lower()

    if mime in {"application/pdf"} or content.startswith(b"%PDF-") or path.endswith(".pdf"):
        return "PDF"
    if mime.startswith("image/") or content.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"GIF87a", b"GIF89a", b"RIFF")):
        return "IMAGE"
    if mime in {"text/html", "application/xhtml+xml"} or path.endswith((".html", ".htm")):
        return "HTML"
    if content.lstrip().lower().startswith((b"<!doctype html", b"<html", b"<head")):
        return "HTML"
    return "UNKNOWN"


def _pdf_text(content: bytes) -> Tuple[str, Dict[str, Any]]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("PDF extraction requires the optional 'pypdf' dependency") from exc

    reader = PdfReader(io.BytesIO(content))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    text = "\n\n".join(p.strip() for p in pages if p.strip())
    return text, {"page_count": len(reader.pages), "text_extraction": "pypdf"}


def _image_ocr(content: bytes) -> Tuple[str, Dict[str, Any]]:
    try:
        from PIL import Image
        import pytesseract
    except ImportError as exc:
        raise RuntimeError(
            "Image OCR requires optional 'pillow' and 'pytesseract' dependencies plus a Tesseract binary"
        ) from exc

    image = Image.open(io.BytesIO(content))
    text = pytesseract.image_to_string(image, lang="ind+eng")
    return text.strip(), {
        "ocr_engine": "tesseract",
        "ocr_language": "ind+eng",
        "image_size": [image.width, image.height],
    }


def extract_non_html(url: str, content_type: str, content: bytes) -> AcquiredContent:
    """Extract text from a downloaded PDF/image without performing network I/O."""
    document_type = detect_document_type(url, content_type, content)
    if document_type == "PDF":
        try:
            text, metadata = _pdf_text(content)
            return AcquiredContent(200, content, content_type, "PDF", text=text, metadata=metadata)
        except Exception as exc:
            return AcquiredContent(200, content, content_type, "PDF", metadata={"extraction_error": str(exc)}, error=str(exc))
    if document_type == "IMAGE":
        try:
            text, metadata = _image_ocr(content)
            return AcquiredContent(200, content, content_type, "IMAGE", text=text, metadata=metadata)
        except Exception as exc:
            return AcquiredContent(200, content, content_type, "IMAGE", metadata={"ocr_error": str(exc)}, error=str(exc))
    return AcquiredContent(200, content, content_type, document_type, error="Unsupported non-HTML content type")


def looks_dynamic_html(html: str) -> bool:
    """Heuristic for pages where static HTML contains little useful content."""
    if not html:
        return False
    lower = html.lower()
    text = re.sub(r"<[^>]+>", " ", html)
    text_len = len(re.sub(r"\s+", " ", text).strip())
    app_markers = ("__next_data__", "id=\"__next\"", "data-reactroot", "webpack", "vite")
    return text_len < 500 and any(marker in lower for marker in app_markers)


def render_dynamic_page(url: str) -> Optional[Tuple[bytes, Dict[str, Any]]]:
    """Render a JS page when Playwright is installed; otherwise return None."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=60000)
            html = page.content().encode("utf-8")
            return html, {"dynamic_rendered": True, "renderer": "playwright"}
        finally:
            browser.close()
