"""Extract, resolve and store the promotions of ONE crawled page.

Used by both the real scan (scripts/run_pipeline.py) and the dry run (scripts/dry_run.py), so a dry run exercises
exactly the code path a real scan does.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any, Callable, Dict, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.source import CrawlDocument
from app.services.channels import normalize_channel
from app.services.entity_resolution.product import resolve_product_result
from app.services.entity_resolution.resolver import EntityResolver
from app.services.entity_resolution.review import persist_resolution_reviews
from app.services.extraction.cards import split_into_cards
from app.services.geography import appears_in_source, clean_wording
from app.services.promotions.upsert import upsert_promotion_observation

logger = logging.getLogger("Pipeline")

GOOD_STATUSES = {"SUCCESS", "PARTIAL_SUCCESS"}
Event = Dict[str, Any]


def process_document(
    db: Session,
    doc: CrawlDocument,
    *,
    extractor,
    resolver: EntityResolver,
    reliability: float,
    summary: Dict[str, Any],
    on_event: Optional[Callable[[Event], None]] = None,
) -> bool:
    """Returns True when every batch of the page was extracted successfully (so the page counts as processed)."""
    emit = on_event or (lambda event: None)
    batch_size = max(1, settings.CARDS_PER_LLM_BATCH)

    cards, total_cards = split_into_cards(doc.text_content, max_cards=settings.MAX_CARDS_PER_DOCUMENT)
    if total_cards > len(cards):
        dropped = total_cards - len(cards)
        summary["cards_truncated"] = summary.get("cards_truncated", 0) + dropped
        logger.warning(
            "Document %s has %d cards; only the first %d are processed (%d skipped). "
            "Raise MAX_CARDS_PER_DOCUMENT to process all.",
            doc.id, total_cards, len(cards), dropped,
        )
    logger.info("Splitting into %d item cards...", len(cards))

    doc_ok = True
    for i in range(0, len(cards), batch_size):
        batch = cards[i:i + batch_size]
        chunk = "\n\n".join(batch)
        logger.info("Extracting batch %d (%d cards)...", i // batch_size + 1, len(batch))

        result = extractor.extract_with_metadata(chunk)
        summary["rejected"] = summary.get("rejected", 0) + len(result.rejected_items)
        if result.parser_status not in GOOD_STATUSES:
            doc_ok = False
        logger.info(
            "Batch extraction status=%s accepted=%d rejected=%d",
            result.parser_status, len(result.items), len(result.rejected_items),
        )
        emit({"type": "batch", "status": result.parser_status, "accepted": len(result.items), "rejected": len(result.rejected_items)})
        for rejected in result.rejected_items:
            emit({"type": "rejected", "error": rejected.get("error"), "item": rejected.get("item")})

        raw_response_hash = (
            hashlib.sha256(result.raw_response.encode("utf-8")).hexdigest()
            if result.raw_response else None
        )
        metadata = {
            "model": result.model,
            "status": result.parser_status,
            "extracted_at": result.extracted_at,
            "raw_response_hash": raw_response_hash,
            "rejected_count": len(result.rejected_items),
        }

        for item in result.items:
            summary["extracted"] = summary.get("extracted", 0) + 1
            # Where a promotion is valid must come from the page itself; unsupported wording is dropped
            # (the promotion is kept with unknown geography) rather than trusted.
            item.geography = clean_wording(item.geography)
            if item.geography and not appears_in_source(item.geography, chunk):
                logger.warning("Dropping geography %r for %r: not found in the source text.", item.geography, item.product_name)
                item.geography = None
                summary["geography_dropped"] = summary.get("geography_dropped", 0) + 1
                emit({"type": "geography_dropped", "product": item.product_name})

            retailer_result = resolver.resolve_retailer_result(item.retailer)
            brand_result, competitor_result = resolver.resolve_brand_and_competitor_result(
                item.brand, item.product_name,
            )
            product_result = resolve_product_result(
                db,
                item.product_name,
                brand_result.entity.id if brand_result.status == "RESOLVED" and brand_result.entity else None,
                sku=getattr(item, "sku", None),
                barcode=getattr(item, "barcode", None),
                pack_size=item.pack_size,
            )
            resolved_entities = {
                "retailer_id": retailer_result.entity.id if retailer_result.status == "RESOLVED" else None,
                "brand_id": brand_result.entity.id if brand_result.status == "RESOLVED" else None,
                "competitor_id": competitor_result.entity.id if competitor_result.status == "RESOLVED" else None,
                "product_id": product_result.entity.id if product_result.status == "RESOLVED" else None,
                "competitor_importance": (
                    competitor_result.entity.importance_score
                    if competitor_result.status == "RESOLVED" and competitor_result.entity else None
                ),
            }

            # Savepoint per item: one bad row must not poison the whole document.
            try:
                with db.begin_nested():
                    promotion, observation, created = upsert_promotion_observation(
                        db,
                        document_id=doc.id,
                        item=item,
                        resolved_entities=resolved_entities,
                        raw_text=chunk,
                        extracted_json=item.model_dump(),
                        observed_at=result.extracted_at,
                        source_url=doc.url,
                        extraction_metadata=metadata,
                        source_reliability=reliability,
                        source_id=doc.source_id,
                    )
                    if promotion.channel is None and retailer_result.status == "RESOLVED" and retailer_result.entity:
                        promotion.channel = normalize_channel(retailer_result.entity.channel_type)
                    review_items = persist_resolution_reviews(
                        db,
                        observation_id=observation.id,
                        promotion_id=promotion.id,
                        resolutions=(
                            ("RETAILER", item.retailer, retailer_result),
                            ("BRAND", item.brand, brand_result),
                            ("COMPETITOR", item.competitor, competitor_result),
                            ("PRODUCT", item.product_name, product_result),
                        ),
                    )
                    summary["review_items"] = summary.get("review_items", 0) + review_items
                summary["created"] = summary.get("created", 0) + int(created)
                summary["observations"] = summary.get("observations", 0) + 1
                emit({"type": "stored", "item": item, "promotion": promotion, "observation": observation, "created": created,
                      "review_items": review_items,
                      "resolutions": {"retailer": retailer_result.status, "brand": brand_result.status,
                                      "competitor": competitor_result.status, "product": product_result.status}})
            except ValueError as validation_error:
                logger.warning("Rejected promotion from document %s: %s", doc.id, validation_error)
                emit({"type": "invalid", "item": item, "error": str(validation_error)})
            except Exception as exc:
                doc_ok = False
                logger.exception("Failed to store promotion from document %s", doc.id)
                emit({"type": "error", "item": item, "error": f"{type(exc).__name__}: {exc}"})
    return doc_ok
