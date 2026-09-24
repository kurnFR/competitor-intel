"""End-to-end PostgreSQL gate for acquisition -> resolution -> canonical promotion."""

from datetime import datetime, timezone
import hashlib
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entity import Brand, Competitor, Product, Retailer
from app.models.promotion import Promotion, PromotionEvidence, PromotionObservation
from app.models.promotion_change import PromotionChangeEvent
from app.models.resolution import ReviewQueue
from app.models.source import CrawlDocument, CrawlJob, SourceRegistry
from app.schemas.ai import ExtractedPromotionItem
from app.services.entity_resolution.product import resolve_product_result
from app.services.entity_resolution.resolver import EntityResolver
from app.services.entity_resolution.review import persist_resolution_reviews
from app.services.promotions.upsert import upsert_promotion_observation
from app.services.entity_resolution.resolver import normalize_str


DATABASE_URL = __import__("os").getenv("DATABASE_URL")


@pytest.fixture(scope="module")
def db_engine():
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL is required for PostgreSQL integration tests")
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
    except Exception as exc:
        engine.dispose()
        pytest.skip(f"PostgreSQL is not reachable: {exc}")
    yield engine
    engine.dispose()


def test_crawl_to_canonical_promotion_and_idempotency(db_engine):
    """Exercise real PostgreSQL persistence across the core pipeline stages."""
    db = Session(db_engine)
    try:
        suffix = uuid.uuid4().hex[:10]
        now = datetime.now(timezone.utc)

        competitor = Competitor(
            name=f"Competitor {suffix}",
            normalized_name=normalize_str(f"Competitor {suffix}"),
            importance_score=0.8,
        )
        db.add(competitor)
        db.flush()

        brand = Brand(
            competitor_id=competitor.id,
            name=f"Brand {suffix}",
            normalized_name=normalize_str(f"Brand {suffix}"),
        )
        db.add(brand)
        db.flush()

        product = Product(
            brand_id=brand.id,
            name=f"Product {suffix}",
            normalized_name=normalize_str(f"Product {suffix}"),
            category="BISCUIT",
            pack_size_value=120,
            pack_size_unit="g",
            sku=f"SKU-{suffix}",
        )
        retailer = Retailer(
            name=f"Retailer {suffix}",
            normalized_name=normalize_str(f"Retailer {suffix}"),
        )
        db.add_all([product, retailer])
        db.flush()

        source = SourceRegistry(
            name=f"Synthetic Source {suffix}",
            domain="synthetic.example",
            base_url="https://synthetic.example/promotions",
            source_type="RETAILER",
            reliability_score=0.95,
            country="ID",
            language="id",
        )
        db.add(source)
        db.flush()

        url = f"https://synthetic.example/promotions/{suffix}"
        raw_text = (
            f"PROMO: {product.name} {product.pack_size_value:g}{product.pack_size_unit} "
            f"Rp20.000 menjadi Rp15.000. Berlaku 24-09-2026 sampai 30-09-2026."
        )
        raw_bytes = raw_text.encode("utf-8")
        content_hash = hashlib.sha256(raw_bytes).hexdigest()

        job = CrawlJob(
            source_id=source.id,
            url=url,
            job_type="CATALOG",
            status="SUCCESS",
            http_status=200,
            content_hash=content_hash,
            started_at=now,
            completed_at=now,
            last_attempt_at=now,
        )
        db.add(job)
        db.flush()

        document = CrawlDocument(
            crawl_job_id=job.id,
            source_id=source.id,
            url=url,
            canonical_url=url,
            document_type="HTML",
            title="Synthetic promotion",
            raw_content_sha256=content_hash,
            raw_content_type="text/html",
            raw_content_size_bytes=len(raw_bytes),
            storage_backend="INLINE_TEST",
            text_content=raw_text,
            content_hash=content_hash,
            retrieved_at=now,
            language="id",
            http_status=200,
            metadata_json={"synthetic": True, "gate": "postgres-e2e"},
        )
        db.add(document)
        db.flush()

        item = ExtractedPromotionItem(
            product_name=product.name,
            brand=brand.name,
            competitor=competitor.name,
            category="BISCUIT",
            pack_size="120g",
            regular_price=20000,
            promo_price=15000,
            promotion_type="DISCOUNT",
            start_date="2026-09-24",
            end_date="2026-09-30",
            retailer=retailer.name,
            evidence_quote="Rp20.000 menjadi Rp15.000",
            confidence=0.97,
        )

        resolver = EntityResolver(db)
        retailer_result = resolver.resolve_retailer_result(item.retailer)
        brand_result, competitor_result = resolver.resolve_brand_and_competitor_result(
            item.brand, item.product_name
        )
        product_result = resolve_product_result(
            db,
            item.product_name,
            brand_result.entity.id if brand_result.entity else None,
            sku=getattr(item, "sku", None),
            pack_size=item.pack_size,
        )
        assert retailer_result.status == "RESOLVED"
        assert brand_result.status == "RESOLVED"
        assert competitor_result.status == "RESOLVED"
        assert product_result.status == "RESOLVED"

        resolved = {
            "retailer_id": retailer_result.entity.id,
            "brand_id": brand_result.entity.id,
            "competitor_id": competitor_result.entity.id,
            "product_id": product_result.entity.id,
            "competitor_importance": competitor.importance_score,
        }
        metadata = {
            "model": "synthetic-test",
            "status": "SUCCESS",
            "extracted_at": now,
            "raw_response_hash": hashlib.sha256(b"synthetic-llm-response").hexdigest(),
            "rejected_count": 0,
        }

        promotion, observation, created = upsert_promotion_observation(
            db,
            document_id=document.id,
            item=item,
            resolved_entities=resolved,
            raw_text=raw_text,
            extracted_json=item.model_dump(),
            observed_at=now,
            source_url=url,
            extraction_metadata=metadata,
            source_reliability=source.reliability_score,
        )
        db.flush()

        assert created is True
        assert promotion.product_id == product.id
        assert promotion.brand_id == brand.id
        assert promotion.competitor_id == competitor.id
        assert promotion.retailer_id == retailer.id
        assert promotion.promo_price == 15000
        assert promotion.discount_percentage == 25
        assert observation.promotion_id == promotion.id
        assert observation.document_id == document.id

        evidence = (
            db.query(PromotionEvidence)
            .filter(PromotionEvidence.promotion_id == promotion.id)
            .all()
        )
        events = (
            db.query(PromotionChangeEvent)
            .filter(PromotionChangeEvent.promotion_id == promotion.id)
            .all()
        )
        assert len(evidence) == 1
        assert evidence[0].document_id == document.id
        assert len(events) == 1
        assert events[0].event_type == "CREATED"

        # Reprocessing the same document must reuse the canonical promotion,
        # observation, evidence and change event rather than multiplying rows.
        promotion_2, observation_2, created_2 = upsert_promotion_observation(
            db,
            document_id=document.id,
            item=item,
            resolved_entities=resolved,
            raw_text=raw_text,
            extracted_json=item.model_dump(),
            observed_at=now,
            source_url=url,
            extraction_metadata=metadata,
            source_reliability=source.reliability_score,
        )
        db.flush()

        assert created_2 is False
        assert promotion_2.id == promotion.id
        assert observation_2.id == observation.id
        assert db.query(Promotion).filter(Promotion.id == promotion.id).count() == 1
        assert (
            db.query(PromotionObservation)
            .filter(PromotionObservation.document_id == document.id)
            .count()
            == 1
        )
        assert (
            db.query(PromotionEvidence)
            .filter(PromotionEvidence.promotion_id == promotion.id)
            .count()
            == 1
        )
        assert (
            db.query(PromotionChangeEvent)
            .filter(PromotionChangeEvent.promotion_id == promotion.id)
            .count()
            == 1
        )

        # Verify the unresolved branch persists human-review work without
        # silently creating a canonical brand/product/competitor.
        unresolved_item = ExtractedPromotionItem(
            product_name=f"Unknown Product {suffix}",
            brand=f"Unknown Brand {suffix}",
            competitor=None,
            category="BISCUIT",
            promo_price=10000,
            promotion_type="DISCOUNT",
            retailer=retailer.name,
            evidence_quote="Rp10.000",
            confidence=0.72,
        )
        unknown_brand, unknown_competitor = resolver.resolve_brand_and_competitor_result(
            unresolved_item.brand, unresolved_item.product_name
        )
        unknown_product = resolve_product_result(
            db,
            unresolved_item.product_name,
            unknown_brand.entity.id if unknown_brand.entity else None,
            pack_size=unresolved_item.pack_size,
        )
        unknown_resolved = {
            "retailer_id": retailer.id,
            "brand_id": unknown_brand.entity.id if unknown_brand.entity else None,
            "competitor_id": unknown_competitor.entity.id if unknown_competitor.entity else None,
            "product_id": unknown_product.entity.id if unknown_product.entity else None,
        }
        unknown_promotion, unknown_observation, _ = upsert_promotion_observation(
            db,
            document_id=document.id,
            item=unresolved_item,
            resolved_entities=unknown_resolved,
            raw_text=unresolved_item.evidence_quote,
            extracted_json=unresolved_item.model_dump(),
            observed_at=now,
            source_url=url,
            extraction_metadata=metadata,
        )
        review_count = persist_resolution_reviews(
            db,
            observation_id=unknown_observation.id,
            promotion_id=unknown_promotion.id,
            resolutions=[
                ("RETAILER", unresolved_item.retailer, retailer_result),
                ("BRAND", unresolved_item.brand, unknown_brand),
                ("COMPETITOR", unresolved_item.competitor, unknown_competitor),
                ("PRODUCT", unresolved_item.product_name, unknown_product),
            ],
        )
        db.flush()

        assert review_count >= 2
        pending = (
            db.query(ReviewQueue)
            .filter(
                ReviewQueue.observation_id == unknown_observation.id,
                ReviewQueue.status == "PENDING",
            )
            .all()
        )
        assert len(pending) == review_count
        assert all(row.promotion_id == unknown_promotion.id for row in pending)

        # The same review persistence call must be idempotent.
        assert (
            persist_resolution_reviews(
                db,
                observation_id=unknown_observation.id,
                promotion_id=unknown_promotion.id,
                resolutions=[
                    ("BRAND", unresolved_item.brand, unknown_brand),
                    ("COMPETITOR", unresolved_item.competitor, unknown_competitor),
                    ("PRODUCT", unresolved_item.product_name, unknown_product),
                ],
            )
            == 0
        )

        db.commit()
    finally:
        db.close()
