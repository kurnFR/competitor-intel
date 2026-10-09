"""Dry run: uses the real pipeline code, explains outcomes, and never saves anything."""
import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.entity import Brand, Competitor
from app.models.promotion import Promotion, PromotionEvidence, PromotionObservation
from app.models.resolution import ReviewQueue
from app.models.source import CrawlDocument, SourceRegistry
from app.schemas.ai import ExtractedPromotionItem
from app.services.dry_run import run_dry
from app.services.extraction.llm_extractor import ExtractionResult

PAGE = "Roma Kelapa 300g diskon 30% jadi Rp 7.000 berlaku di wilayah Jawa. Beli 2 gratis 1 Malkist Abon."


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        session.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"PostgreSQL is not reachable: {exc}")
    yield session
    session.rollback()
    session.close()


class FakeExtractor:
    def __init__(self, items, rejected=None, status="SUCCESS"):
        self.items, self.rejected, self.status = items, rejected or [], status

    def extract_with_metadata(self, chunk):
        return ExtractionResult(items=[i.model_copy() for i in self.items], rejected_items=self.rejected, raw_response="{}",
                                model="fake", extracted_at=datetime.now(timezone.utc), parser_status=self.status)


def item(**kw):
    base = dict(product_name="Zz Dry Roma Kelapa 300g", brand="Zz Unknown Brand", category="BISCUIT", pack_size="300g", regular_price=10000,
                promo_price=7000, discount_percentage=30, promotion_type="DISCOUNT", retailer="Indomaret",
                evidence_quote="diskon 30% jadi Rp 7.000", confidence=0.9)
    base.update(kw)
    return ExtractedPromotionItem(**base)


def counts(db):
    db.rollback()
    return {m.__tablename__: db.query(m).count() for m in (Promotion, SourceRegistry, CrawlDocument, PromotionObservation,
                                                           PromotionEvidence, ReviewQueue, Brand, Competitor)}


def test_nothing_is_saved_even_though_the_real_storage_code_ran(db):
    before = counts(db)
    report = run_dry(PAGE, extractor=FakeExtractor([item(), item(product_name="Zz Dry Other", brand="Zz Another Unknown")]))
    assert report["persisted"] is False and report["summary"]["stored"] == 2
    assert counts(db) == before                                  # promotions, sources, documents, evidence, review items, brands: all unchanged
    again = run_dry(PAGE, extractor=FakeExtractor([item()]))
    assert again["items"][0]["outcome"] == "NEW"                  # a second run does not see the first run's rows
    assert counts(db) == before


def test_unmatched_brand_is_hidden_with_the_reason_and_the_fix(db):
    r = run_dry(PAGE, extractor=FakeExtractor([item()]))
    (i,) = r["items"]
    assert i["shown"] is False and i["matched"]["brand"] != "RESOLVED"
    assert [w["key"] for w in i["hidden_because"]] == ["identity"]
    assert "Review page" in i["hidden_because"][0]["fix"]
    assert r["summary"]["would_be_shown"] == 0 and i["review_items"] >= 1


def test_the_same_item_is_shown_when_the_identity_rule_is_relaxed(db, monkeypatch):
    monkeypatch.setattr(settings, "TOP10_REQUIRE_RESOLVED_IDENTITY", False)
    (i,) = run_dry(PAGE, extractor=FakeExtractor([item()]))["items"]
    assert i["shown"] is True and i["hidden_because"] == [] and i["promo_price"] == "Rp7,000" and i["discount_percentage"] == 30


def test_geography_must_appear_in_the_page(db, monkeypatch):
    monkeypatch.setattr(settings, "TOP10_REQUIRE_RESOLVED_IDENTITY", False)
    r = run_dry(PAGE, extractor=FakeExtractor([item(geography="Jawa"), item(product_name="Zz Dry Two", geography="Papua")]))
    java, papua = r["items"]
    assert java["geography"] == "Jawa" and java["region"] == "Jawa"
    assert papua["geography"] is None and papua["region"] == "Not stated"           # invented location dropped, not trusted
    assert r["geography_dropped"] == ["Zz Dry Two"]


def test_retailer_hint_is_used_only_when_the_page_names_none(db, monkeypatch):
    monkeypatch.setattr(settings, "TOP10_REQUIRE_RESOLVED_IDENTITY", False)
    r = run_dry(PAGE, extractor=FakeExtractor([item(retailer=None), item(product_name="Zz Dry Named", retailer="Alfamart")]), retailer_name="Indomaret")
    assert r["items"][0]["matched"]["retailer"] == "RESOLVED" and r["items"][0]["channel"] == "Modern Trade"
    assert r["items"][1]["channel"] == "Modern Trade"


def test_rejected_items_and_failed_batches_are_reported(db):
    rejected = [{"error": "Evidence quote not found in source text", "item": {"product_name": "Zz Dry Bad"}}]
    r = run_dry(PAGE, extractor=FakeExtractor([item()], rejected=rejected))
    assert r["rejected"][0]["reason"].startswith("Evidence quote") and r["summary"]["rejected"] == 1
    broken = run_dry(PAGE, extractor=FakeExtractor([], status="ERROR"))
    assert broken["all_batches_ok"] is False and broken["items"] == []


def test_cli_helpers_replay_html_and_print(tmp_path, db, capsys):
    import scripts.dry_run as cli
    html = tmp_path / "p.html"
    html.write_text("<html><head><style>x{}</style><script>var a=1</script></head><body><h1>Promo</h1><p>Roma 300g diskon 30%</p></body></html>")
    page = cli.read_page(str(html))
    assert "Roma 300g diskon 30%" in page and "var a" not in page and "x{}" not in page

    saved = tmp_path / "items.json"
    saved.write_text(json.dumps({"promotions": [item().model_dump(mode="json")]}))
    report = run_dry(PAGE, extractor=cli.Replay(str(saved)))
    assert report["summary"]["stored"] == 1
    cli.print_report(report)
    out = capsys.readouterr().out
    assert "WOULD APPEAR ON THE DASHBOARD: NO" in out and "No competitor or brand could be matched" in out and "Nothing was saved." in out
