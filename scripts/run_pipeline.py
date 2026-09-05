import hashlib
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.source import CrawlDocument, SourceRegistry
from app.models.promotion import Promotion
from app.services.crawler.manager import run_all_crawlers
from app.services.entity_resolution.resolver import EntityResolver
from app.services.extraction.llm_extractor import LLMExtractor
from app.services.promotions.upsert import upsert_promotion_observation

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("Pipeline")


def run_pipeline(crawl_fresh: bool = False, max_docs: int = 3):
    db: Session = SessionLocal()
    try:
        logger.info("Starting Competitor Intel Extraction & Promotion Pipeline...")

        docs = []
        if crawl_fresh:
            logger.info("Executing active crawlers...")
            docs = run_all_crawlers(db)
        else:
            docs = db.query(CrawlDocument).order_by(CrawlDocument.retrieved_at.desc()).limit(max_docs).all()
            if not docs:
                logger.info("No existing documents found. Triggering crawlers...")
                docs = run_all_crawlers(db)

        logger.info(f"Processing {len(docs)} documents through AI Extraction & Validation...")

        extractor = LLMExtractor()
        resolver = EntityResolver(db)

        total_extracted = 0
        total_canonical_created = 0
        total_observations = 0
        total_rejected = 0

        for doc in docs:
            logger.info(f"Document {doc.id} ({doc.url}) text length: {len(doc.text_content or '')}")
            if not doc.text_content:
                continue

            source = doc.source or db.query(SourceRegistry).filter(SourceRegistry.id == doc.source_id).first()
            reliability = source.reliability_score if source else 0.85

            # Split catalog into bounded blocks so one large catalog does not
            # exceed the LLM context/output budget.
            cards = [c.strip() for c in doc.text_content.split("---") if len(c.strip()) > 30]
            logger.info(f"Splitting into {len(cards)} item cards...")

            chunk_size = 6
            for i in range(0, min(len(cards), 30), chunk_size):
                chunk = "\n\n".join(cards[i:i + chunk_size])
                logger.info(f"Extracting batch {i // chunk_size + 1} ({len(cards[i:i + chunk_size])} cards)...")

                result = extractor.extract_with_metadata(chunk)
                total_rejected += len(result.rejected_items)
                logger.info(
                    "Batch extraction status=%s accepted=%d rejected=%d",
                    result.parser_status,
                    len(result.items),
                    len(result.rejected_items),
                )

                raw_response_hash = (
                    hashlib.sha256(result.raw_response.encode("utf-8")).hexdigest()
                    if result.raw_response
                    else None
                )
                metadata = {
                    "model": result.model,
                    "status": result.parser_status,
                    "extracted_at": result.extracted_at,
                    "raw_response_hash": raw_response_hash,
                    "rejected_count": len(result.rejected_items),
                }

                for item in result.items:
                    total_extracted += 1

                    retailer_result = resolver.resolve_retailer_result(item.retailer)
                    brand_result, competitor_result = resolver.resolve_brand_and_competitor_result(
                        item.brand,
                        item.product_name,
                    )
                    resolved_entities = {
                        "retailer_id": retailer_result.entity.id if retailer_result.status == "RESOLVED" else None,
                        "brand_id": brand_result.entity.id if brand_result.status == "RESOLVED" else None,
                        "competitor_id": competitor_result.entity.id if competitor_result.status == "RESOLVED" else None,
                    }

                    try:
                        _, _, created = upsert_promotion_observation(
                            db,
                            document_id=doc.id,
                            item=item,
                            resolved_entities=resolved_entities,
                            raw_text=item.evidence_quote,
                            extracted_json=item.model_dump(),
                            observed_at=result.extracted_at,
                            source_url=doc.url,
                            extraction_metadata=metadata,
                            source_reliability=reliability,
                        )
                        total_canonical_created += int(created)
                        total_observations += 1
                    except ValueError as validation_error:
                        logger.warning(
                            "Rejected promotion from document %s: %s",
                            doc.id,
                            validation_error,
                        )

            db.commit()

        logger.info("Pipeline execution finished!")
        logger.info(f"Total AI Observations: {total_observations}")
        logger.info(f"Total Newly Canonical Promotions: {total_canonical_created}")
        logger.info(f"Total Extracted Items: {total_extracted}")
        logger.info(f"Total LLM-Rejected Items: {total_rejected}")
        logger.info(
            "Total Canonical Active Promotions: %s",
            db.query(Promotion).filter(Promotion.status == "ACTIVE").count(),
        )

    except Exception as e:
        logger.error(f"Pipeline error: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    run_pipeline()
