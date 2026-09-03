import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.source import CrawlDocument, SourceRegistry
from app.models.promotion import PromotionObservation, Promotion
from app.services.crawler.manager import run_all_crawlers
from app.services.extraction.llm_extractor import LLMExtractor
from app.services.deduplication.deduplicator import PromotionDeduplicator

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
        deduplicator = PromotionDeduplicator(db)

        total_extracted = 0
        total_canonical = 0

        for doc in docs:
            logger.info(f"Document {doc.id} ({doc.url}) text length: {len(doc.text_content or '')}")
            if not doc.text_content:
                continue

            # Split catalog into blocks of ~5 cards to ensure complete LLM extraction without token truncation
            cards = [c.strip() for c in doc.text_content.split("---") if len(c.strip()) > 30]
            logger.info(f"Splitting into {len(cards)} item cards...")

            chunk_size = 6
            for i in range(0, min(len(cards), 30), chunk_size):
                chunk = "\n\n".join(cards[i:i + chunk_size])
                logger.info(f"Extracting batch {i // chunk_size + 1} ({len(cards[i:i + chunk_size])} cards)...")

                items = extractor.extract_from_text(chunk)
                logger.info(f"Batch returned {len(items)} structured promotions.")

                for item in items:
                    total_extracted += 1
                    # Record observation
                    obs = PromotionObservation(
                        document_id=doc.id,
                        raw_text=item.evidence_quote,
                        extracted_json=item.model_dump(),
                        ai_confidence=item.confidence,
                        observed_at=datetime.now(timezone.utc),
                        created_at=datetime.now(timezone.utc)
                    )
                    db.add(obs)
                    db.flush()

                    # Deduplicate, resolve, score, and persist
                    source = doc.source or db.query(SourceRegistry).filter(SourceRegistry.id == doc.source_id).first()
                    reliability = source.reliability_score if source else 0.85

                    promo = deduplicator.process_and_save(item, doc, source_reliability=reliability)
                    if promo:
                        total_canonical += 1

            db.commit()

        logger.info(" Pipeline execution finished!")
        logger.info(f"Total AI Observations: {total_extracted}")
        logger.info(f"Total Canonical Active Promotions: {db.query(Promotion).filter(Promotion.status == 'ACTIVE').count()}")

    except Exception as e:
        logger.error(f"Pipeline error: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    run_pipeline()
