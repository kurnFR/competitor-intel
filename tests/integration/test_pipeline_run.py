"""Pipeline behaviour on PostgreSQL: unchanged-page skipping, errors, locking, channels."""
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

import scripts.run_pipeline as rp
from app.db.session import SessionLocal, engine
from app.models.promotion import Promotion, PromotionEvidence, PromotionObservation
from app.models.promotion_change import PromotionChangeEvent
from app.models.source import CrawlDocument, SourceRegistry
from app.schemas.ai import ExtractedPromotionItem
from app.services.extraction.llm_extractor import ExtractionResult


@pytest.fixture()
def synthetic_doc():
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
    except Exception as exc:  # no database available
        pytest.skip(f"PostgreSQL is not reachable: {exc}")
    suffix = uuid.uuid4().hex[:8]
    quote = f"Zzyx{suffix} Biskuit Kelapa 300g Rp7.000 diskon 30%"
    source = SourceRegistry(name=f"Pipeline Test {suffix}", domain=f"pipe-{suffix}.example",
                            base_url=f"https://pipe-{suffix}.example/", source_type="RETAILER",
                            reliability_score=0.9, country="ID", language="id", is_active=False)
    db.add(source)
    db.flush()
    doc = CrawlDocument(source_id=source.id, url=source.base_url, text_content=quote + " " + "x" * 40,
                        content_hash=uuid.uuid4().hex + uuid.uuid4().hex, http_status=200)
    db.add(doc)
    db.commit()
    ctx = {"db": db, "doc": doc, "source": source, "quote": quote, "suffix": suffix}
    yield ctx
    db.rollback()
    promo_ids = [r[0] for r in db.query(Promotion.id).filter(Promotion.product_name.like(f"Zzyx{suffix}%")).all()]
    if promo_ids:
        db.query(PromotionChangeEvent).filter(PromotionChangeEvent.promotion_id.in_(promo_ids)).delete(synchronize_session=False)
        db.query(PromotionEvidence).filter(PromotionEvidence.promotion_id.in_(promo_ids)).delete(synchronize_session=False)
        db.query(PromotionObservation).filter(PromotionObservation.promotion_id.in_(promo_ids)).delete(synchronize_session=False)
        db.query(Promotion).filter(Promotion.id.in_(promo_ids)).delete(synchronize_session=False)
    db.query(CrawlDocument).filter(CrawlDocument.source_id == source.id).delete(synchronize_session=False)
    db.query(SourceRegistry).filter(SourceRegistry.id == source.id).delete(synchronize_session=False)
    db.commit()
    db.close()


class FakeExtractor:
    calls = 0
    status = "SUCCESS"

    def __init__(self, ctx):
        self.ctx = ctx

    def extract_with_metadata(self, chunk):
        FakeExtractor.calls += 1
        item = ExtractedPromotionItem(
            product_name=f"Zzyx{self.ctx['suffix']} Biskuit Kelapa 300g", brand="Roma", competitor="Mayora",
            category="BISCUIT", pack_size="300g", regular_price=10000, promo_price=7000, discount_percentage=30,
            promotion_type="DISCOUNT", retailer="Indomaret", evidence_quote=self.ctx["quote"], confidence=0.95,
        )
        return ExtractionResult(items=[item], rejected_items=[], raw_response="{}", model="fake",
                                extracted_at=datetime.now(timezone.utc), parser_status=FakeExtractor.status)


def _patch(monkeypatch, ctx):
    FakeExtractor.calls, FakeExtractor.status = 0, "SUCCESS"
    monkeypatch.setattr(rp, "LLMExtractor", lambda: FakeExtractor(ctx))
    monkeypatch.setattr(rp, "run_all_crawlers", lambda db, **kw: [db.get(CrawlDocument, ctx["doc"].id)])


def _promo(ctx):
    ctx["db"].expire_all()
    return ctx["db"].query(Promotion).filter(Promotion.product_name.like(f"Zzyx{ctx['suffix']}%")).one()


def test_undated_promo_is_stored_visible_and_channel_filled(monkeypatch, synthetic_doc):
    _patch(monkeypatch, synthetic_doc)
    summary = rp.run_pipeline(crawl_fresh=True, max_docs=None)
    assert summary["status"] == "completed" and summary["observations"] == 1 and summary["created"] == 1
    promo = _promo(synthetic_doc)
    assert promo.status == "UNKNOWN" and promo.start_date is None and promo.end_date is None
    assert promo.channel == "Modern Trade"  # derived from the retailer, not left as N/A
    assert promo.source_id == synthetic_doc["source"].id             # promotion is linked to its source
    assert promo.geography is None and promo.geography_region == "UNKNOWN"   # nothing stated -> unknown, not nationwide
    synthetic_doc["db"].refresh(synthetic_doc["source"])
    assert synthetic_doc["source"].last_processed_at is not None      # fully processed -> counts as a successful check


def test_unchanged_page_skips_llm_but_keeps_promotion_fresh(monkeypatch, synthetic_doc):
    _patch(monkeypatch, synthetic_doc)
    rp.run_pipeline(crawl_fresh=True, max_docs=None)
    assert FakeExtractor.calls == 1
    first_seen = _promo(synthetic_doc).last_seen_at

    summary = rp.run_pipeline(crawl_fresh=True, max_docs=None)
    assert FakeExtractor.calls == 1  # no second LLM call for an identical page
    assert summary["documents_skipped_unchanged"] == 1
    again = _promo(synthetic_doc)
    assert again.last_seen_at > first_seen and again.last_verified_at > first_seen   # re-confirmed by the unchanged page

    rp.run_pipeline(crawl_fresh=True, max_docs=None, force=True)
    assert FakeExtractor.calls == 2


def test_failed_extraction_is_retried_next_run(monkeypatch, synthetic_doc):
    _patch(monkeypatch, synthetic_doc)
    FakeExtractor.status = "ERROR"
    summary = rp.run_pipeline(crawl_fresh=True, max_docs=None)
    assert summary["documents_failed"] == 1
    synthetic_doc["db"].refresh(synthetic_doc["source"])
    assert synthetic_doc["source"].last_processed_at is None          # a failed extraction is NOT a successful check of the source
    FakeExtractor.status = "SUCCESS"
    summary = rp.run_pipeline(crawl_fresh=True, max_docs=None)
    assert summary["documents_skipped_unchanged"] == 0 and summary["observations"] == 1
    synthetic_doc["db"].refresh(synthetic_doc["source"])
    assert synthetic_doc["source"].last_processed_at is not None      # recovered on the retry


def test_pipeline_errors_are_raised_not_swallowed(monkeypatch, synthetic_doc):
    def boom(db, **kw):
        raise RuntimeError("crawler exploded")
    monkeypatch.setattr(rp, "run_all_crawlers", boom)
    with pytest.raises(RuntimeError):
        rp.run_pipeline(crawl_fresh=True, max_docs=None)


def test_concurrent_run_is_refused(monkeypatch, synthetic_doc):
    _patch(monkeypatch, synthetic_doc)
    with engine.connect() as other:
        other.execute(text("SELECT pg_advisory_lock(:k)"), {"k": rp._PIPELINE_LOCK_KEY})
        try:
            assert rp.run_pipeline(crawl_fresh=True, max_docs=None) == {"status": "busy"}
        finally:
            other.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": rp._PIPELINE_LOCK_KEY})
            other.commit()


def test_geography_is_kept_only_when_the_page_states_it(monkeypatch, synthetic_doc):
    _patch(monkeypatch, synthetic_doc)

    class GeoExtractor(FakeExtractor):
        wording = "Jawa"

        def extract_with_metadata(self, chunk):
            result = super().extract_with_metadata(chunk)
            result.items[0].geography = GeoExtractor.wording
            return result

    monkeypatch.setattr(rp, "LLMExtractor", lambda: GeoExtractor(synthetic_doc))
    GeoExtractor.wording = "Papua"                       # the page does not mention Papua -> invented, must be dropped
    summary = rp.run_pipeline(crawl_fresh=True, max_docs=None)
    assert summary["geography_dropped"] == 1
    promo = _promo(synthetic_doc)
    assert promo.geography is None and promo.geography_region == "UNKNOWN"


def test_an_unchanged_page_still_reconfirms_its_promotions_even_if_its_text_was_trimmed(monkeypatch, synthetic_doc):
    """Retention removes old page text; a stable page must not stop re-confirming its promotions because of that."""
    _patch(monkeypatch, synthetic_doc)
    rp.run_pipeline(crawl_fresh=True, max_docs=None)
    first_verified = _promo(synthetic_doc).last_verified_at
    doc = synthetic_doc["db"].get(CrawlDocument, synthetic_doc["doc"].id)
    doc.text_content = None
    synthetic_doc["db"].commit()
    summary = rp.run_pipeline(crawl_fresh=True, max_docs=None)
    assert summary["documents_skipped_unchanged"] == 1
    assert _promo(synthetic_doc).last_verified_at > first_verified
