import io
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.session import SessionLocal
from app.main import app
from app.models.auth import AuditLog, User
from app.models.entity import Competitor, Retailer
from app.models.own_product import OwnProduct
from app.models.promotion import Promotion
from app.services import auth as auth_service
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
    users = {}
    for role in ("VIEWER", "ANALYST"):
        users[role] = f"cmp_{role.lower()}_{tag}"
        auth_service.create_user(db, username=users[role], password=PASSWORD, role=role)
    db.commit()
    retailer = db.query(Retailer).first()
    competitor = db.query(Competitor).first()
    now = datetime.now(timezone.utc)
    promos = []
    source = make_source(db, tag)
    db.commit()

    def promo(name, **kw):
        base = dict(product_name=f"Zz{tag} {name}", retailer_id=retailer.id, competitor_id=competitor.id)
        base.update(kw)
        p = add_promotion(db, source, **base)
        promos.append(p)
        return p

    def login(role):
        c = TestClient(app, follow_redirects=False)
        r = c.post("/api/v1/auth/login", json={"username": users[role], "password": PASSWORD})
        assert r.status_code == 200
        return c, {"X-CSRF-Token": r.json()["csrf_token"]}

    yield type("Ctx", (), dict(db=db, tag=tag, promo=staticmethod(promo), login=staticmethod(login)))
    db.rollback()
    db.query(OwnProduct).filter(OwnProduct.name.like(f"Zz{tag}%")).delete(synchronize_session=False)
    db.query(OwnProduct).filter(OwnProduct.sku.like(f"SKU-{tag}%")).delete(synchronize_session=False)
    cleanup_source(db, source)
    for name in users.values():
        db.query(AuditLog).filter(AuditLog.username == name).delete(synchronize_session=False)
        db.query(User).filter(User.username == name).delete(synchronize_session=False)
    db.commit()
    db.close()


def test_comparison_flags_cheaper_competitor_and_ignores_incomparable(env, monkeypatch):
    from app.services import comparison
    monkeypatch.setattr(comparison, "MAX_MATCHES", 10_000)     # other rows in a shared database must not crowd ours out
    # Our pack: 300 g at Rp12,000 -> Rp4,000 / 100 g
    env.promo("Cheaper", pack_size="300g", promo_price=9000)                                  # 3,000/100g -> -25%
    env.promo("Dearer", pack_size="300g", promo_price=15000)                                  # 5,000/100g -> +25%
    env.promo("B2G1", pack_size="300g", promo_price=9000, promotion_type="BUY_X_GET_Y",       # 2,000/100g -> -50%
              buy_quantity=2, free_quantity=1)
    env.promo("Tiny pack", pack_size="50g", promo_price=1000)                                 # ratio 0.17 -> excluded
    env.promo("Other category", pack_size="300g", promo_price=1000, category="WAFER")         # excluded
    env.promo("No price", pack_size="300g")                                                   # cannot compute
    env.promo("Unknown pack", promo_price=1000)                                               # cannot compute
    env.db.commit()

    c, hdr = env.login("ANALYST")
    r = c.post("/api/v1/compare/products", json={"name": f"Zz{env.tag} Ours", "pack_size": "300g", "regular_price": 12000}, headers=hdr)
    assert r.status_code == 201 and r.json()["pack_grams"] == 300
    c.post("/api/v1/compare/products", json={"name": f"Zz{env.tag} No pack", "regular_price": 5000}, headers=hdr)

    data = c.get("/api/v1/compare/").json()
    ours = next(p for p in data["products"] if p["name"] == f"Zz{env.tag} Ours")
    assert ours["price_per_100g"] == 4000
    mine = [m for m in ours["comparable"] if m["product"].startswith(f"Zz{env.tag}")]
    assert [m["product"].split(" ", 1)[1] for m in mine] == ["B2G1", "Cheaper", "Dearer"]      # cheapest first
    assert [m["gap_pct"] for m in mine] == [-50.0, -25.0, 25.0]
    assert [m["undercuts_us"] for m in mine] == [True, True, False]
    assert ours["undercut_count"] >= 2 and ours["largest_gap_pct"] <= -50.0
    nopack = next(p for p in data["products"] if p["name"] == f"Zz{env.tag} No pack")
    assert nopack["price_per_100g"] is None and "pack size" in nopack["note"].lower()


def test_permissions_and_validation(env):
    viewer, vhdr = env.login("VIEWER")
    assert viewer.get("/api/v1/compare/").status_code == 403
    assert viewer.get("/compare").status_code == 303
    analyst, hdr = env.login("ANALYST")
    body = {"name": f"Zz{env.tag} X", "regular_price": 5000}
    assert analyst.post("/api/v1/compare/products", json=body).status_code == 403                      # CSRF
    assert analyst.post("/api/v1/compare/products", json={**body, "regular_price": 0}, headers=hdr).status_code == 422
    assert analyst.post("/api/v1/compare/products", json={**body, "category": "SOAP"}, headers=hdr).status_code == 422
    created = analyst.post("/api/v1/compare/products", json=body, headers=hdr).json()
    upd = analyst.patch(f"/api/v1/compare/products/{created['id']}", json={"pack_size": "1 kg", "regular_price": 8000}, headers=hdr)
    assert upd.status_code == 200 and upd.json()["pack_grams"] == 1000
    assert analyst.delete(f"/api/v1/compare/products/{created['id']}", headers=hdr).status_code == 204
    assert analyst.delete(f"/api/v1/compare/products/{created['id']}", headers=hdr).status_code == 404
    assert analyst.get("/compare").status_code == 200


def test_csv_import_is_all_or_nothing_and_upserts_by_sku(env):
    c, hdr = env.login("ANALYST")
    good = (f"name,brand,category,pack_size,regular_price,sku\n"
            f"Zz{env.tag} A,Mine,BISCUIT,300g,\"Rp 10.500\",SKU-{env.tag}-1\n"
            f"Zz{env.tag} B,Mine,wafer,150 g,7500,SKU-{env.tag}-2\n")
    files = lambda content, name="p.csv": {"file": (name, io.BytesIO(content.encode()), "text/csv")}
    r = c.post("/api/v1/compare/products/import", files=files(good), headers=hdr)
    assert r.status_code == 200 and r.json() == {"created": 2, "updated": 0}

    again = good.replace("10.500", "11.000")
    r = c.post("/api/v1/compare/products/import", files=files(again), headers=hdr)
    assert r.json() == {"created": 0, "updated": 2}
    row = env.db.query(OwnProduct).filter(OwnProduct.sku == f"SKU-{env.tag}-1").one()
    env.db.refresh(row)
    assert row.regular_price == 11000 and row.pack_grams == 300

    bad = (f"name,regular_price,category\nZz{env.tag} C,5000,BISCUIT\nZz{env.tag} D,abc,BISCUIT\nZz{env.tag} E,4000,SOAP\n")
    r = c.post("/api/v1/compare/products/import", files=files(bad), headers=hdr)
    assert r.status_code == 422
    assert {e["line"] for e in r.json()["detail"]["errors"]} == {3, 4}
    assert env.db.query(OwnProduct).filter(OwnProduct.name == f"Zz{env.tag} C").count() == 0   # nothing saved

    assert c.post("/api/v1/compare/products/import", files=files("foo,bar\n1,2\n"), headers=hdr).status_code == 422
    assert c.post("/api/v1/compare/products/import", files=files("x" * 1_100_000), headers=hdr).status_code == 413
