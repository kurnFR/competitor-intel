"""Split crawled page text into promotion 'cards' for LLM extraction."""
from __future__ import annotations

import re
from typing import List, Tuple

_SEPARATOR = re.compile(r"^\s*(?:-{3,}|={3,}|\*{3,})\s*$", re.MULTILINE)


def split_into_cards(text: str, *, max_cards: int, fallback_chunk_chars: int = 1500) -> Tuple[List[str], int]:
    """Return (cards, total_found). Never silently drops content beyond max_cards.

    Aggregator-style pages separate cards with a horizontal rule. Pages without
    separators are split on blank lines and packed into ~fallback_chunk_chars
    chunks so a long page is still processed in full.
    """
    text = (text or "").strip()
    if not text:
        return [], 0

    parts = [p.strip() for p in _SEPARATOR.split(text) if p.strip()]
    if len(parts) <= 1:
        parts = _pack_paragraphs(text, fallback_chunk_chars)

    total = len(parts)
    return parts[:max_cards], total


def _pack_paragraphs(text: str, limit: int) -> List[str]:
    chunks: List[str] = []
    current: List[str] = []
    size = 0
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        # A single oversized paragraph is cut on line boundaries.
        pieces = [para] if len(para) <= limit else _cut_lines(para, limit)
        for piece in pieces:
            if current and size + len(piece) > limit:
                chunks.append("\n\n".join(current))
                current, size = [], 0
            current.append(piece)
            size += len(piece)
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def _cut_lines(text: str, limit: int) -> List[str]:
    out: List[str] = []
    buf: List[str] = []
    size = 0
    for line in text.splitlines():
        if buf and size + len(line) + 1 > limit:
            out.append("\n".join(buf))
            buf, size = [], 0
        buf.append(line[:limit])
        size += len(line) + 1
    if buf:
        out.append("\n".join(buf))
    return out
