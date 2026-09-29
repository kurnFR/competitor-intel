import hashlib
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal, engine
from app.models.promotion import Promotion, PromotionObservation
from app.models.source import CrawlDocument, SourceRegistry
from app.services.channels import normalize_channel
from app.services.crawler.manager import run_all_crawlers
from app.services.entity_resolution.product import resolve_product_result
from app.services.entity_resolution.resolver import EntityResolver
from app.services.entity_resolution.review import persist_resolution_reviews
from app.services.extraction.cards import split_into_cards
from app.services.extraction.llm_extractor import LLMExtractor
from app.services.promotions.upsert import upsert_promotion_observation
from app.services.ranking.rescore import rescore_promotions

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("Pipeline")

# Arbitrary constant identifying the pipeline's cross-process advisory lock.
_PIPELINE_LOCK_KEY = 7_204_118_301
_GOOD_STATUSES = {"SUCCESS", "PARTIAL_SUCCESS"}


def _acquire_lock():
    """Take a Postgres advisory lock on a dedicated connection.

    Prevents the scheduler, a manual "Scan now" and extra uvicorn workers from
    running the pipeline at the same time. Returns (connection, acquired).
    """
    conn = engine.connect()
    if engine.dialect.name != "postgresql":
        return conn, True
    acquired = bool(conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _PIPELINE_LOCK_KEY}).scalar())
    conn.commit()
    return conn, acquired


def _release_lock(conn, acquired: bool) -> None:
    try:
        if acquired and engine.dialect.name == "postgresql":
            conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _PIPELINE_LOCK_KEY})
            conn.commit()
    finally:
        conn.close()


def _touch_promotions_for_document(db: Session, document_id, now: datetime) -> int:
    """An unchanged page that was just re-fetched still confirms its promotions."""
    ids = db.query(PromotionObservation.promotion_id).filter(PromotionObservation.document_id == document_id)
    return (
        db.query(Promotion)
        .filter(Promotion.id.in_(ids), Promotion.status.in_(["ACTIVE", "UNKNOWN"]))
        .update({"last_seen_at": now}, synchronize_session=False)
    )


def run_pipeline(
    crawl_fresh: bool = False,
    max_docs: Optional[int] = 3,
    force: bool = False,
) -> Dict[str, Any]:
    """Crawl (optionally), extract, validate and store promotions.

    Raises on failure so callers (API, scheduler, CLI) can report it truthfully.
    Returns a summary dict; ``status`` is "completed" or "busy" (another run is active).

    max_docs only limits re-processing of stored documents; a fresh crawl always
    processes every document it produced. Documents already processed from an
    identical page are skipped (their promotions are just marked as still seen)
    unless force=True.
    """
    lock_conn, acquired = _acquire_lock()
    if not acquired:
        _release_lock(lock_conn, acquired)
        logger.warning("Pipeline already running in another process; skipping this run.")
        return {"status": "busy"}

    db: Session = SessionLocal()
    summary: Dict[str, Any] = {
        "status": "completed", "documents": 0, "documents_skipped_unchanged": 0,
        "documents_failed": 0, "extracted": 0, "observations": 0, "created": 0,
        "rejected": 0, "review_items": 0, "cards_truncated": 0,
    }
    try:
        logger.info("Starting Competitor Intel Extraction & Promotion Pipeline...")

        if crawl_fresh:
            logger.info("Executing active crawlers...")
            docs = run_all_crawlers(db)
        else:
            query = db.query(CrawlDocument).order_by(CrawlDocument.retrieved_at.desc())
            docs = query.limit(max_docs).all() if max_docs else query.all()
            if not docs:
                logger.info("No existing documents found. Triggering crawlers...")
                docs = run_all_crawlers(db)
                crawl_fresh = True

        logger.info("Processing %d documents through AI Extraction & Validation...", len(docs))
        summary["documents"] = len(docs)

        extractor = LLMExtractor()
        resolver = EntityResolver(db)
        batch_size = max(1, settings.CARDS_PER_LLM_BATCH)

        for doc in docs:
            logger.info("Document %s (%s) text length: %d", doc.id, doc.url, len(doc.text_content or ""))
            if not doc.text_content:
                continue

            now = datetime.now(timezone.utc)
            already_done = bool((doc.metadata_json or {}).get("pipeline_processed_at"))
            if already_done and not force:
                if crawl_fresh:
                    _touch_promotions_for_document(db, doc.id, now)
                    db.commit()
                summary["documents_skipped_unchanged"] += 1
                logger.info("Document %s unchanged since last extraction; skipping LLM call.", doc.id)
                continue

            source = doc.source or db.query(SourceRegistry).filter(SourceRegistry.id == doc.source_id).first()
            reliability = source.reliability_score if source else 0.85

            cards, total_cards = split_into_cards(doc.text_content, max_cards=settings.MAX_CARDS_PER_DOCUMENT)
            if total_cards > len(cards):
                dropped = total_cards - len(cards)
                summary["cards_truncated"] += dropped
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
                summary["rejected"] += len(result.rejected_items)
                if result.parser_status not in _GOOD_STATUSES:
                    doc_ok = False
                logger.info(
                    "Batch extraction status=%s accepted=%d rejected=%d",
                    result.parser_status, len(result.items), len(result.rejected_items),
                )

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
                    summary["extracted"] += 1

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
                            )
                            if promotion.channel is None and retailer_result.status == "RESOLVED" and retailer_result.entity:
                                promotion.channel = normalize_channel(retailer_result.entity.channel_type)
                            summary["review_items"] += persist_resolution_reviews(
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
                        summary["created"] += int(created)
                        summary["observations"] += 1
                    except ValueError as validation_error:
                        logger.warning("Rejected promotion from document %s: %s", doc.id, validation_error)
                    except Exception:
                        doc_ok = False
                        logger.exception("Failed to store promotion from document %s", doc.id)

            if doc_ok:
                doc.metadata_json = {**(doc.metadata_json or {}), "pipeline_processed_at": now.isoformat()}
            else:
                summary["documents_failed"] += 1
                logger.warning("Document %s had extraction errors and will be retried next run.", doc.id)
            db.commit()

        # Keep freshness-based ranking current after this run.
        rescored = rescore_promotions(db)
        db.commit()
        logger.info("Rescored %d promotions.", rescored)

        logger.info("Pipeline execution finished! %s", summary)
        return summary

    except Exception:
        logger.exception("Pipeline error")
        db.rollback()
        raise
    finally:
        db.close()
        _release_lock(lock_conn, acquired)


if __name__ == "__main__":
    try:
        result = run_pipeline()
    except Exception:
        sys.exit(1)
    sys.exit(0 if result.get("status") in ("completed", "busy") else 1)
