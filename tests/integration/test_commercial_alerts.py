"""Commercial and Marketing Intelligence Alert tests.

Validates that:
1. Deep discounts trigger PRICE_SHOCK alerts once.
2. BOGO / Buy-Get promotions trigger DISRUPTIVE_PROMO alerts once.
3. Competitor price per 100g undercutting our own products triggers COMPETITOR_UNDERCUT alerts.
4. Alerts are delivered via configured notification channels.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.db.session import SessionLocal
from app.models.alert import AlertEvent
from app.models.entity import Brand, Competitor, Retailer
from app.models.own_product import OwnProduct
from app.models.promotion import Promotion, PromotionEvidence
from app.models.source import SourceRegistry
from app.services import alerts

NOW = datetime.now(timezone.utc)


@pytest.fixture()
def comm_env(monkeypatch):
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"PostgreSQL is not reachable: {exc}")

    created_promos = []
    created_own = []
    created_sources = []
    created_alerts = []

    # Mock notification channels
    sent = []
    state = {"channels": True, "result": {"email": True, "webhook": True}}
    monkeypatch.setattr(alerts.notify, "any_channel_configured", lambda: state["channels"])
    monkeypatch.setattr(alerts.notify, "send_text", lambda subject, body: (sent.append((subject, body)) or dict(state["result"])))

    # Setup competitor and retailer
    comp = db.query(Competitor).filter(Competitor.name == "Mayora").first()
    if not comp:
        comp = Competitor(name="Mayora", normalized_name="mayora", is_active=True)
        db.add(comp)
        db.flush()

    ret = db.query(Retailer).filter(Retailer.name == "Indomaret").first()
    if not ret:
        ret = Retailer(name="Indomaret")
        db.add(ret)
        db.flush()

    src = SourceRegistry(
        name=f"CommTest Src {uuid.uuid4().hex[:6]}",
        domain=f"comm-{uuid.uuid4().hex[:6]}.example",
        base_url="https://comm.example/",
        source_type="RETAILER",
        adapter_key="generic_catalog",
        approval_status="APPROVED",
        is_active=True,
        last_crawled_at=NOW,
        last_success_at=NOW,
    )
    db.add(src)
    db.flush()
    created_sources.append(src.id)

    db.commit()

    def make_promo(**kw):
        base = dict(
            competitor_id=comp.id,
            retailer_id=ret.id,
            source_id=src.id,
            product_name=f"Test Biscuit {uuid.uuid4().hex[:6]}",
            category="BISCUIT",
            pack_size="300g",
            regular_price=20000.0,
            promo_price=14000.0,
            discount_percentage=30.0,
            promotion_type="DISCOUNT",
            status="ACTIVE",
            geography_region="JAWA",
            first_seen_at=NOW,
            last_seen_at=NOW,
            last_verified_at=NOW,
            rank_score=80.0,
        )
        base.update(kw)
        p = Promotion(**base)
        db.add(p)
        db.flush()

        ev = PromotionEvidence(
            promotion_id=p.id,
            evidence_text=f"Promo {p.product_name} Diskon {p.discount_percentage}%",
            evidence_type="CATALOG_TEXT",
        )
        db.add(ev)
        db.commit()
        created_promos.append(p.id)
        return p

    def make_own(**kw):
        base = dict(
            name=f"Our Biscuit {uuid.uuid4().hex[:6]}",
            brand="OurBrand",
            category="BISCUIT",
            pack_size="300g",
            pack_grams=300.0,
            regular_price=25000.0,  # ~83.33 per 100g
            is_active=True,
        )
        base.update(kw)
        o = OwnProduct(**base)
        db.add(o)
        db.commit()
        created_own.append(o.id)
        return o

    yield type("Env", (), dict(db=db, make_promo=make_promo, make_own=make_own, sent=sent, state=state))

    # Teardown
    db.rollback()
    for pid in created_promos:
        db.query(AlertEvent).filter(AlertEvent.subject_id == str(pid)).delete(synchronize_session=False)
    for oid in created_own:
        db.query(AlertEvent).filter(AlertEvent.fingerprint.like(f"%{oid}%")).delete(synchronize_session=False)
    db.query(Promotion).filter(Promotion.id.in_(created_promos)).delete(synchronize_session=False)
    db.query(OwnProduct).filter(OwnProduct.id.in_(created_own)).delete(synchronize_session=False)
    db.query(SourceRegistry).filter(SourceRegistry.id.in_(created_sources)).delete(synchronize_session=False)
    db.commit()
    db.close()


def test_price_shock_alert_detected_and_delivered(comm_env):
    db = comm_env.db
    # Create promo with 35% discount (well above 20% threshold)
    p = comm_env.make_promo(discount_percentage=35.0, regular_price=20000.0, promo_price=13000.0)

    alerts_res = alerts.check_and_alert(db, now=NOW)
    assert alerts_res["new"] >= 1
    assert alerts_res["sent"] >= 1

    # Verify AlertEvent record
    event = db.query(AlertEvent).filter(AlertEvent.subject_id == str(p.id), AlertEvent.kind == "PRICE_SHOCK").first()
    assert event is not None
    assert "Price Shock" in event.title
    assert "35%" in event.title
    assert event.delivered is True

    # Check deduplication: running check_and_alert again shouldn't create duplicate
    again = alerts.check_and_alert(db, now=NOW)
    dup_count = db.query(AlertEvent).filter(AlertEvent.subject_id == str(p.id), AlertEvent.kind == "PRICE_SHOCK").count()
    assert dup_count == 1


def test_disruptive_promo_bogo_alert(comm_env):
    db = comm_env.db
    p = comm_env.make_promo(
        promotion_type="BUY_X_GET_Y",
        buy_quantity=1,
        free_quantity=1,
        regular_price=15000.0,
        promo_price=15000.0,
        discount_percentage=None,
    )

    alerts_res = alerts.check_and_alert(db, now=NOW)
    event = db.query(AlertEvent).filter(AlertEvent.subject_id == str(p.id), AlertEvent.kind == "DISRUPTIVE_PROMO").first()
    assert event is not None
    assert "Disruptive Promo" in event.title
    assert "BUY_X_GET_Y" in event.title or "Buy 1 Get 1" in event.title


def test_competitor_undercut_alert(comm_env):
    db = comm_env.db
    # Our product: 300g for 30,000 -> 10,000 per 100g
    own = comm_env.make_own(pack_grams=300.0, regular_price=30000.0)

    # Competitor promo: 300g for 15,000 -> 5,000 per 100g (-50% undercut!)
    p = comm_env.make_promo(pack_size="300g", regular_price=20000.0, promo_price=15000.0, discount_percentage=25.0)

    alerts_res = alerts.check_and_alert(db, now=NOW)
    event = db.query(AlertEvent).filter(AlertEvent.kind == "COMPETITOR_UNDERCUT").first()
    assert event is not None
    assert "Price Undercut" in event.title
    assert "undercuts" in event.body
