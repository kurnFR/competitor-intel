"""PRD invariants: eligibility gates, verification vs sighting, failed crawl != gone, honest geography."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.config import settings
from app.db.session import SessionLocal
from app.main import app
from app.models.auth import AuditLog, User
from app.models.promotion import Promotion, PromotionEvidence, PromotionObservation
from app.models.source import CrawlDocument, SourceRegistry
from app.schemas.ai import ExtractedPromotionItem
from app.services import auth as auth_service
from app.services.promotions.identity import promotion_source_identity_fingerprint
from app.services.promotions.upsert import upsert_promotion_observation
from app.workers.expiration import run_expiration_check
from tests.helpers import add_promotion, cleanup_source, make_source

PASSWORD = "Correct-Horse-Battery-9"


@pytest.fixture()
def env():
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"PostgreSQL is not reachable: {exc}")
    auth_service.ip_throttle.clear()
    tag = uuid.uuid4().hex[:8]
    name = f"prd_{tag}"
    auth_service.create_user(db, username=name, password=PASSWORD, role="ANALYST")
    db.commit()
    sources = []

    def source(**kw):
        s = make_source(db, uuid.uuid4().hex[:6], **kw)
        db.commit()
        sources.append(s)
        return s

    def client():
        c = TestClient(app, follow_redirects=False)
        assert c.post("/api/v1/auth/login", json={"username": name, "password": PASSWORD}).status_code == 200
        return c

    def visible(c):
        items = c.get(f"/api/v1/promotions/top10?q=Zz{tag}").json()["promotions"]
        return {i["product_name"].split(" ", 1)[1] for i in items}

    yield type("Env", (), dict(db=db, tag=tag, source=staticmethod(source), client=staticmethod(client),
                               visible=staticmethod(visible), now=datetime.now(timezone.utc)))
    db.rollback()
    for s in sources:
        cleanup_source(db, s)
    db.query(AuditLog).filter(AuditLog.username == name).delete(synchronize_session=False)
    db.query(User).filter(User.username == name).delete(synchronize_session=False)
    db.commit()
    db.close()
    auth_service.ip_throttle.clear()


# ---------------------------------------------------------------- eligibility gates (PRD 14)
def test_every_gate_is_enforced_independently(env):
    ok = env.source()
    candidate = env.source(approved=False)
    paused = env.source(active=False)
    n = lambda label: f"Zz{env.tag} {label}"
    add_promotion(env.db, ok, product_name=n("Eligible"))
    add_promotion(env.db, ok, product_name=n("No evidence"), evidence=False)
    add_promotion(env.db, ok, product_name=n("Blank evidence"), evidence=False)
    blank = env.db.query(Promotion).filter(Promotion.product_name == n("Blank evidence")).one()
    env.db.add(PromotionEvidence(promotion_id=blank.id, evidence_text="   ", source_url="https://x.test"))
    add_promotion(env.db, candidate, product_name=n("Unapproved source"))
    add_promotion(env.db, paused, product_name=n("Paused source"))
    add_promotion(env.db, None, product_name=n("No source"))
    add_promotion(env.db, ok, product_name=n("Seen but not verified"), last_seen_at=env.now,
                  last_verified_at=env.now - timedelta(days=120))
    add_promotion(env.db, ok, product_name=n("Not listed"), status="NOT_LISTED")
    add_promotion(env.db, ok, product_name=n("Expired"), status="EXPIRED")
    add_promotion(env.db, ok, product_name=n("Past end date"), end_date=env.now - timedelta(hours=1))
    env.db.commit()
    assert env.visible(env.client()) == {"Eligible"}


def test_verification_window_follows_the_days_parameter(env):
    ok = env.source()
    add_promotion(env.db, ok, product_name=f"Zz{env.tag} Month old", last_verified_at=env.now - timedelta(days=40))
    env.db.commit()
    c = env.client()
    assert "Month old" in env.visible(c)
    items = c.get(f"/api/v1/promotions/top10?q=Zz{env.tag}&days=30").json()["promotions"]
    assert items == []


def test_api_reports_last_verified_not_last_seen(env):
    ok = env.source()
    verified = env.now - timedelta(days=3)
    add_promotion(env.db, ok, product_name=f"Zz{env.tag} Verified", last_seen_at=env.now, last_verified_at=verified)
    env.db.commit()
    item = env.client().get(f"/api/v1/promotions/top10?q=Zz{env.tag}").json()["promotions"][0]
    assert item["last_verified"].startswith(verified.strftime("%Y-%m-%d"))


# ---------------------------------------------------------------- failed crawl is not "zero promotions" (PRD 5)
def test_expiration_only_concludes_absence_after_a_successful_later_processing(env):
    grace = timedelta(days=settings.UNDATED_PROMO_MAX_AGE_DAYS)
    old = env.now - grace - timedelta(days=5)           # verified long ago

    failing = env.source()           # never processed since: crawl/extraction failing
    failing.last_processed_at = old - timedelta(days=1)
    healthy = env.source()           # processed recently and no longer lists the promotion
    healthy.last_processed_at = env.now
    never = env.source()             # never processed at all
    p_failing = add_promotion(env.db, failing, product_name=f"Zz{env.tag} F", status="UNKNOWN", last_verified_at=old)
    p_healthy = add_promotion(env.db, healthy, product_name=f"Zz{env.tag} H", status="UNKNOWN", last_verified_at=old)
    p_never = add_promotion(env.db, never, product_name=f"Zz{env.tag} N", status="UNKNOWN", last_verified_at=old)
    p_recent = add_promotion(env.db, healthy, product_name=f"Zz{env.tag} R", status="UNKNOWN", last_verified_at=env.now - timedelta(days=1))
    p_dated = add_promotion(env.db, healthy, product_name=f"Zz{env.tag} D", status="ACTIVE", last_verified_at=old,
                            start_date=env.now - timedelta(days=60), end_date=env.now + timedelta(days=3))
    env.db.commit()

    run_expiration_check(env.db)
    env.db.expire_all()
    status = lambda p: env.db.get(Promotion, p.id).status
    assert status(p_failing) == "UNKNOWN"      # source has not been successfully processed since -> no conclusion
    assert status(p_never) == "UNKNOWN"
    assert status(p_healthy) == "NOT_LISTED"   # source processed fine and no longer lists it
    assert status(p_recent) == "UNKNOWN"       # verified recently, still listed
    assert status(p_dated) == "ACTIVE"         # dated promotions follow their own end date, not absence


def test_explicit_expiry_overrides_freshness(env):
    ok = env.source()
    p = add_promotion(env.db, ok, product_name=f"Zz{env.tag} Fresh but over", last_verified_at=env.now,
                      end_date=env.now - timedelta(minutes=5))
    env.db.commit()
    run_expiration_check(env.db)
    env.db.expire_all()
    assert env.db.get(Promotion, p.id).status == "EXPIRED"
    assert "Fresh but over" not in env.visible(env.client())


# ---------------------------------------------------------------- honest geography (PRD 9) and legacy identity
def _item(**kw):
    base = dict(product_name="Zz Roma Kelapa 300g", brand="Roma", competitor="Mayora", category="BISCUIT", pack_size="300g",
                regular_price=10000, promo_price=7000, discount_percentage=30, promotion_type="DISCOUNT", retailer="Indomaret",
                evidence_quote="Roma Kelapa 300g Rp7.000", confidence=0.9)
    base.update(kw)
    return ExtractedPromotionItem(**base)


def _document(env, source):
    doc = CrawlDocument(source_id=source.id, url=source.base_url, text_content="Roma Kelapa 300g Rp7.000",
                        content_hash=uuid.uuid4().hex + uuid.uuid4().hex, http_status=200)
    env.db.add(doc)
    env.db.flush()
    return doc


def test_unstated_geography_is_unknown_not_nationwide_and_wording_is_kept(env):
    src = env.source()
    doc = _document(env, src)
    tag = env.tag
    p1, _, _ = upsert_promotion_observation(env.db, document_id=doc.id, item=_item(product_name=f"Zz{tag} A"),
                                            raw_text="Roma Kelapa 300g Rp7.000", source_id=src.id)
    p2, _, _ = upsert_promotion_observation(env.db, document_id=doc.id, item=_item(product_name=f"Zz{tag} B", geography="Pulau  Jawa"),
                                            raw_text="Roma Kelapa 300g Rp7.000", source_id=src.id)
    assert p1.geography is None and p1.geography_region == "UNKNOWN"
    assert p2.geography == "Pulau Jawa" and p2.geography_region == "JAWA"      # verbatim kept, region normalised
    assert p1.source_id == src.id and p1.last_verified_at is not None


def test_same_product_in_two_regions_stays_two_promotions(env):
    src = env.source()
    doc = _document(env, src)
    kw = dict(document_id=doc.id, raw_text="Roma Kelapa 300g Rp7.000", source_id=src.id)
    a, _, ca = upsert_promotion_observation(env.db, item=_item(product_name=f"Zz{env.tag} X", geography="Jawa"), **kw)
    b, _, cb = upsert_promotion_observation(env.db, item=_item(product_name=f"Zz{env.tag} X", geography="Sumatera", promo_price=8500), **kw)
    again, _, cc = upsert_promotion_observation(env.db, item=_item(product_name=f"Zz{env.tag} X", geography="Pulau Jawa"), **kw)
    assert ca and cb and a.id != b.id
    assert not cc and again.id == a.id                      # wording variant of the same region is the same promotion


def test_legacy_promotions_with_the_old_fake_default_are_matched_not_duplicated(env):
    """Rows created before the fix carry geography 'Indonesia' in their identity hash."""
    src = env.source()
    doc = _document(env, src)
    item = _item(product_name=f"Zz{env.tag} Legacy")
    legacy_fp = promotion_source_identity_fingerprint({
        "retailer": item.retailer, "brand": item.brand, "competitor": item.competitor, "product_name": item.product_name,
        "sku": None, "pack_size": item.pack_size, "promotion_type": item.promotion_type, "channel": None, "geography": "Indonesia"})
    old = add_promotion(env.db, src, product_name=item.product_name, pack_size=item.pack_size, promotion_type="DISCOUNT",
                        source_identity_fingerprint=legacy_fp, identity_fingerprint="legacy-" + uuid.uuid4().hex,
                        identity_version="v2", geography=None)
    env.db.commit()
    before = env.db.query(Promotion).filter(Promotion.product_name == item.product_name).count()
    promo, _, created = upsert_promotion_observation(env.db, document_id=doc.id, item=item, raw_text="Roma Kelapa 300g Rp7.000",
                                                     source_id=src.id)
    assert not created and promo.id == old.id                                    # recognised, not duplicated
    assert env.db.query(Promotion).filter(Promotion.product_name == item.product_name).count() == before
    assert promo.source_identity_fingerprint != legacy_fp                        # re-stamped with the honest fingerprint
    again, _, created2 = upsert_promotion_observation(env.db, document_id=doc.id, item=item, raw_text="Roma Kelapa 300g Rp7.000",
                                                      source_id=src.id)
    assert not created2 and again.id == old.id


def test_region_filter_and_display_in_the_api(env):
    src = env.source()
    add_promotion(env.db, src, product_name=f"Zz{env.tag} Java", geography="Jawa", geography_region="JAWA")
    add_promotion(env.db, src, product_name=f"Zz{env.tag} Unknown")
    env.db.commit()
    c = env.client()
    all_items = {i["product_name"].split(" ", 1)[1]: i for i in c.get(f"/api/v1/promotions/top10?q=Zz{env.tag}").json()["promotions"]}
    assert all_items["Java"]["geography"] == "Jawa" and all_items["Java"]["geography_region"] == "JAWA"
    assert all_items["Unknown"]["geography"] == "Not stated" and all_items["Unknown"]["geography_region"] == "UNKNOWN"
    only = c.get(f"/api/v1/promotions/top10?q=Zz{env.tag}&region=jawa").json()["promotions"]
    assert [i["product_name"].split(" ", 1)[1] for i in only] == ["Java"]


def test_regional_prices_endpoint_and_page(env):
    src = env.source()
    n = f"Zz{env.tag} Roma"
    add_promotion(env.db, src, product_name=n, pack_size="300g", promo_price=7900, geography="Jawa", geography_region="JAWA")
    add_promotion(env.db, src, product_name=n, pack_size="300g", promo_price=9500, geography="Kalimantan", geography_region="KALIMANTAN")
    add_promotion(env.db, src, product_name=n, pack_size="300g", promo_price=7000)                       # region not stated
    add_promotion(env.db, src, product_name=n + " noprice", pack_size="300g")                           # no price -> omitted
    env.db.commit()
    c = env.client()
    data = c.get(f"/api/v1/promotions/regional-prices?q=Zz{env.tag}").json()
    (product,) = data["products"]
    assert {r: v["min_price"] for r, v in product["cells"].items()} == {"JAWA": 7900, "KALIMANTAN": 9500, "UNKNOWN": 7000}
    assert product["spread_pct"] == 20.3 and product["differs_by_region"]
    assert c.get("/regional").status_code == 200
    assert TestClient(app).get("/api/v1/promotions/regional-prices").status_code == 401


def test_identity_and_optional_geography_gates(env, monkeypatch):
    src = env.source()
    n = lambda label: f"Zz{env.tag} {label}"
    add_promotion(env.db, src, product_name=n("Resolved"), geography="Jawa", geography_region="JAWA")
    add_promotion(env.db, src, product_name=n("Unresolved"), competitor_id=None, brand_id=None)
    add_promotion(env.db, src, product_name=n("Region unstated"))
    env.db.commit()
    c = env.client()
    assert env.visible(c) == {"Resolved", "Region unstated"}              # identity gate on by default

    monkeypatch.setattr(settings, "TOP10_REQUIRE_RESOLVED_IDENTITY", False)
    assert env.visible(c) == {"Resolved", "Unresolved", "Region unstated"}

    monkeypatch.setattr(settings, "TOP10_REQUIRE_KNOWN_GEOGRAPHY", True)   # strict reading of "geography understood"
    assert env.visible(c) == {"Resolved"}


# ---------------------------------------------------------------- multi-source conflicts (PRD 16)
def _two_sources(env, reliability_a=0.85, reliability_b=0.85):
    a, b = env.source(), env.source()
    a.reliability_score, b.reliability_score = reliability_a, reliability_b
    env.db.commit()
    return a, b


def _observe(env, source, price, label, **kw):
    from app.models.entity import Competitor
    doc = _document(env, source)
    competitor = env.db.query(Competitor).first()
    return upsert_promotion_observation(
        env.db, document_id=doc.id, resolved_entities={"competitor_id": competitor.id}, item=_item(product_name=f"Zz{env.tag} {label}", promo_price=price,
                                               discount_percentage=None, regular_price=None, **kw),
        raw_text="Roma Kelapa 300g Rp7.000", source_id=source.id, source_reliability=source.reliability_score,
        observed_at=env.now)


def _pending(env, promo):
    from app.models.resolution import ReviewQueue
    return env.db.query(ReviewQueue).filter(ReviewQueue.promotion_id == promo.id, ReviewQueue.entity_type == "CONFLICT").all()


def test_comparable_sources_disagreeing_freeze_the_values_and_ask_a_person(env):
    a, b = _two_sources(env)
    p1, obs1, _ = _observe(env, a, 7000, "Dispute")
    env.db.commit()
    assert "Dispute" in env.visible(env.client())                     # control: visible while only one source speaks
    p2, obs2, created = _observe(env, b, 6500, "Dispute")
    assert p1.id == p2.id and not created
    assert p2.promo_price == 7000 and p2.source_id == a.id           # nothing was silently overwritten
    assert p2.has_open_conflict is True
    assert obs1.id != obs2.id and obs2.extracted_json["promo_price"] == 6500   # both observations are retained
    (item,) = _pending(env, p2)
    assert item.status == "PENDING" and "Rp7,000 vs Rp6,500" in item.reason
    # re-observing the same disagreement (e.g. a re-crawl of a changed page) does not pile up duplicate review items
    _, newest, _ = _observe(env, b, 6500, "Dispute")
    (item,) = _pending(env, p2)
    assert item.observation_id == newest.id                           # ...and points at the freshest observation
    env.db.commit()
    assert "Dispute" not in env.visible(env.client())                  # hidden from the Top 10 until resolved


def test_more_authoritative_source_wins_automatically_and_less_authoritative_is_kept_out(env):
    a, b = _two_sources(env, reliability_a=0.70, reliability_b=0.95)
    p, _, _ = _observe(env, a, 7000, "Auth")
    p, _, _ = _observe(env, b, 6500, "Auth")
    assert p.promo_price == 6500 and p.source_id == b.id and not p.has_open_conflict and _pending(env, p) == []
    p, obs, _ = _observe(env, a, 9000, "Auth")                          # now the weaker source disagrees
    assert p.promo_price == 6500 and p.source_id == b.id and not p.has_open_conflict
    assert obs.extracted_json["promo_price"] == 9000                    # still on record


def test_stale_facts_are_superseded_by_a_newer_observation(env):
    a, b = _two_sources(env)
    p, _, _ = _observe(env, a, 7000, "Stale")
    p.last_verified_at = env.now - timedelta(days=10)
    p, _, _ = _observe(env, b, 6500, "Stale")
    assert p.promo_price == 6500 and not p.has_open_conflict


def test_analyst_resolves_a_conflict_either_way(env):
    a, b = _two_sources(env)
    p1, _, _ = _observe(env, a, 7000, "Resolve")
    p2, _, _ = _observe(env, b, 6500, "Resolve")
    q1, _, _ = _observe(env, a, 9000, "Resolve Other")
    q2, _, _ = _observe(env, b, 8000, "Resolve Other")
    env.db.commit()
    c = env.client()
    csrf = {"X-CSRF-Token": c.get("/api/v1/auth/me").json()["csrf_token"]}
    items = {i["promotion_id"]: i for i in c.get("/api/v1/review/?limit=200").json() if i["entity_type"] == "CONFLICT"}
    use_new, keep = items[str(p1.id)], items[str(q1.id)]
    assert use_new["can_approve"] is True and "Two sources disagree" in use_new["reason"]

    r = c.post(f"/api/v1/review/{use_new['id']}/resolve", json={"decision": "APPROVED"}, headers=csrf)
    assert r.status_code == 200
    r = c.post(f"/api/v1/review/{keep['id']}/resolve", json={"decision": "REJECTED"}, headers=csrf)
    assert r.status_code == 200
    env.db.expire_all()
    p1, q1 = env.db.get(Promotion, p1.id), env.db.get(Promotion, q1.id)
    assert p1.promo_price == 6500 and p1.source_id == b.id and p1.has_open_conflict is False      # new values adopted
    assert q1.promo_price == 9000 and q1.source_id == a.id and q1.has_open_conflict is False      # current values kept
    assert {"Resolve", "Resolve Other"} <= env.visible(c)                                         # visible again
    assert c.post(f"/api/v1/review/{use_new['id']}/resolve", json={"decision": "APPROVED"}, headers=csrf).status_code == 409
    actions = {a.action for a in env.db.query(AuditLog).filter(AuditLog.action == "conflict_resolved")}
    assert "conflict_resolved" in actions


def test_a_promotion_stays_hidden_until_every_conflict_on_it_is_resolved(env):
    a, b = _two_sources(env)
    c3 = env.source()
    c3.reliability_score = 0.85
    env.db.commit()
    p, _, _ = _observe(env, a, 7000, "Two disputes")
    _observe(env, b, 6500, "Two disputes")
    _observe(env, c3, 6200, "Two disputes")
    env.db.commit()
    assert len(_pending(env, p)) == 2
    c = env.client()
    csrf = {"X-CSRF-Token": c.get("/api/v1/auth/me").json()["csrf_token"]}
    ids = [i["id"] for i in c.get("/api/v1/review/?limit=200").json() if i["promotion_id"] == str(p.id)]
    c.post(f"/api/v1/review/{ids[0]}/resolve", json={"decision": "REJECTED"}, headers=csrf)
    env.db.expire_all()
    assert env.db.get(Promotion, p.id).has_open_conflict is True       # one dispute remains
    c.post(f"/api/v1/review/{ids[1]}/resolve", json={"decision": "REJECTED"}, headers=csrf)
    env.db.expire_all()
    assert env.db.get(Promotion, p.id).has_open_conflict is False
