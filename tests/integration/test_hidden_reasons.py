"""'Why is this promotion hidden?': every Top 10 rule is a named gate; the explanation must agree with the real filter."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.session import SessionLocal
from app.main import app
from app.models.auth import AuditLog, User
from app.services import auth as auth_service
from app.services.promotions.visibility import eligibility_gates, gate_failure_counts, live_promotion_filter, why_hidden
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
    name = f"hid_{tag}"
    auth_service.create_user(db, username=name, password=PASSWORD, role="ANALYST")
    db.commit()
    sources = []

    def source(**kw):
        s = make_source(db, uuid.uuid4().hex[:6], **kw)
        db.commit()
        sources.append(s)
        return s

    def visible():
        c = TestClient(app, follow_redirects=False)
        assert c.post("/api/v1/auth/login", json={"username": name, "password": PASSWORD}).status_code == 200
        items = c.get(f"/api/v1/promotions/top10?q=Zz{tag}").json()["promotions"]
        return {i["product_name"].split(" ", 1)[1] for i in items}

    yield type("Env", (), dict(db=db, tag=tag, now=datetime.now(timezone.utc), source=staticmethod(source), visible=staticmethod(visible)))
    db.rollback()
    for s in sources:
        cleanup_source(db, s)
    db.query(AuditLog).filter(AuditLog.username == name).delete(synchronize_session=False)
    db.query(User).filter(User.username == name).delete(synchronize_session=False)
    db.commit()
    db.close()
    auth_service.ip_throttle.clear()


def test_why_hidden_names_every_failed_gate_and_agrees_with_the_filter(env):
    ok, candidate = env.source(), env.source(approved=False)
    shown = add_promotion(env.db, ok, product_name=f"Zz{env.tag} Shown")
    hidden = add_promotion(env.db, candidate, product_name=f"Zz{env.tag} Hidden", evidence=False, competitor_id=None,
                           has_open_conflict=True, last_verified_at=env.now - timedelta(days=120))
    expired = add_promotion(env.db, ok, product_name=f"Zz{env.tag} Over", status="EXPIRED")
    env.db.commit()

    assert why_hidden(env.db, shown.id) == []
    reasons = why_hidden(env.db, hidden.id)
    assert {r["key"] for r in reasons} == {"verified", "evidence", "source", "conflict", "identity"}
    assert all(r["label"] and r["fix"] for r in reasons)
    assert [r["key"] for r in why_hidden(env.db, expired.id)] == ["active"]

    assert env.visible() == {"Shown"}                              # the dashboard agrees with the explanation
    summary = gate_failure_counts(env.db)
    assert summary["shown"] >= 1 and summary["total"] == summary["shown"] + summary["hidden"]
    assert {g["key"] for g in summary["gates"]} >= {"active", "verified", "evidence", "source", "conflict", "identity"}
    assert [g["count"] for g in summary["gates"]] == sorted((g["count"] for g in summary["gates"]), reverse=True)


def test_filter_and_gates_are_one_definition(env):
    """The SQL used to hide promotions is built from the same gates that explain them."""
    ok = env.source()
    p = add_promotion(env.db, ok, product_name=f"Zz{env.tag} Same")
    env.db.commit()
    from app.models.promotion import Promotion
    n = lambda cond: env.db.query(Promotion).filter(Promotion.id == p.id, cond).count()
    gates = eligibility_gates(env.now, recency_days=90)
    assert n(live_promotion_filter(env.now, recency_days=90)) == 1 and all(n(g.condition) == 1 for g in gates)


def test_optional_gates_appear_only_when_enabled(env, monkeypatch):
    from app.core.config import settings
    keys = lambda: [g.key for g in eligibility_gates(env.now, recency_days=90)]
    assert "identity" in keys() and "geography" not in keys()
    monkeypatch.setattr(settings, "TOP10_REQUIRE_RESOLVED_IDENTITY", False)
    monkeypatch.setattr(settings, "TOP10_REQUIRE_KNOWN_GEOGRAPHY", True)
    assert "identity" not in keys() and "geography" in keys()
    ok = env.source()
    add_promotion(env.db, ok, product_name=f"Zz{env.tag} Nowhere")
    add_promotion(env.db, ok, product_name=f"Zz{env.tag} Java", geography="Jawa", geography_region="JAWA")
    env.db.commit()
    assert env.visible() == {"Java"}
