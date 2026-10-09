"""Run a page through the REAL pipeline code and report what would happen, saving nothing.

Everything happens inside an outer database transaction that is always rolled back, so even if some code path commits,
no row survives. Use it to judge extraction and matching on a real page before approving a website.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.session import engine
from app.models.source import CrawlDocument, SourceRegistry
from app.services.entity_resolution.resolver import EntityResolver
from app.services.geography import REGION_LABELS
from app.services.pipeline_core import process_document
from app.services.promotions.visibility import why_hidden


def _money(value: Any) -> Optional[str]:
    return None if value is None else f"Rp{float(value):,.0f}"


def run_dry(text: str, *, extractor=None, retailer_name: Optional[str] = None, reliability: float = 0.85,
            recency_days: int = 90) -> Dict[str, Any]:
    """Returns a report dict. `extractor` defaults to the real LLM extractor; tests and --extracted pass a stand-in."""
    if extractor is None:
        from app.services.extraction.llm_extractor import LLMExtractor
        extractor = LLMExtractor()
    if retailer_name:
        extractor = _WithRetailer(extractor, retailer_name)

    connection = engine.connect()
    outer = connection.begin()
    db = Session(bind=connection, join_transaction_mode="create_savepoint")
    events: List[Dict[str, Any]] = []
    summary: Dict[str, Any] = {}
    try:
        tag = uuid.uuid4().hex[:8]
        source = SourceRegistry(
            name=f"Dry run {tag}", domain=f"dry-run-{tag}.invalid", base_url=f"https://dry-run-{tag}.invalid/",
            source_type="RETAILER", adapter_key="generic_catalog", approval_status="APPROVED", is_active=True,
            reliability_score=reliability)
        db.add(source)
        db.flush()
        doc = CrawlDocument(source_id=source.id, url=source.base_url, text_content=text, content_hash=uuid.uuid4().hex * 2, http_status=200)
        db.add(doc)
        db.flush()

        ok = process_document(db, doc, extractor=extractor, resolver=EntityResolver(db), reliability=reliability,
                              summary=summary, on_event=events.append)
        db.flush()

        now = datetime.now(timezone.utc)
        items, rejected, batches, dropped = [], [], [], []
        for e in events:
            if e["type"] == "batch":
                batches.append(e)
            elif e["type"] == "rejected":
                rejected.append({"reason": e.get("error"), "item": e.get("item")})
            elif e["type"] == "geography_dropped":
                dropped.append(e["product"])
            elif e["type"] in ("invalid", "error"):
                items.append({"product": e["item"].product_name, "outcome": "INVALID" if e["type"] == "invalid" else "ERROR",
                              "detail": e["error"], "shown": False, "hidden_because": []})
            elif e["type"] == "stored":
                p = e["promotion"]
                hidden = why_hidden(db, p.id, now=now, recency_days=recency_days)
                items.append({
                    "product": p.product_name, "outcome": "NEW" if e["created"] else "MATCHES_EXISTING",
                    "regular_price": _money(p.regular_price), "promo_price": _money(p.promo_price),
                    "discount_percentage": p.discount_percentage, "promotion_type": p.promotion_type, "pack_size": p.pack_size,
                    "start_date": p.start_date.strftime("%Y-%m-%d") if p.start_date else None,
                    "end_date": p.end_date.strftime("%Y-%m-%d") if p.end_date else None,
                    "geography": p.geography, "region": REGION_LABELS.get(p.geography_region, p.geography_region),
                    "channel": p.channel, "matched": e["resolutions"], "review_items": e["review_items"],
                    "has_conflict": bool(p.has_open_conflict), "score": p.rank_score,
                    "shown": not hidden, "hidden_because": hidden,
                    "evidence": (e["item"].evidence_quote or "")[:160],
                })
        return {
            "persisted": False, "page_characters": len(text), "all_batches_ok": ok,
            "batches": [{"status": b["status"], "accepted": b["accepted"], "rejected": b["rejected"]} for b in batches],
            "rejected": rejected, "geography_dropped": dropped, "items": items,
            "summary": {"extracted": summary.get("extracted", 0), "stored": sum(1 for i in items if i["outcome"] in ("NEW", "MATCHES_EXISTING")),
                        "would_be_shown": sum(1 for i in items if i["shown"]), "rejected": len(rejected),
                        "review_items": summary.get("review_items", 0)},
        }
    finally:
        db.close()
        outer.rollback()
        connection.close()


class _WithRetailer:
    """Fills in the retailer when the page does not name one (the real scan gets it from the page text)."""

    def __init__(self, inner, retailer_name: str):
        self.inner, self.retailer_name = inner, retailer_name

    def extract_with_metadata(self, chunk: str):
        result = self.inner.extract_with_metadata(chunk)
        for item in result.items:
            if not item.retailer:
                item.retailer = self.retailer_name
        return result
