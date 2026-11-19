import io
import uuid
from datetime import datetime, timedelta, timezone

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


def test_dual_state_pricing_comparison(env, monkeypatch):
    from app.services import comparison
    monkeypatch.setattr(comparison, "MAX_MATCHES", 10_000)

    # Competitor promos (all 300g)
    env.promo("DeepDiscount", pack_size="300g", promo_price=6000)    # 2,000/100g
    env.promo("MidDiscount", pack_size="300g", promo_price=9000)     # 3,000/100g
    env.promo("Dearer", pack_size="300g", promo_price=15000)         # 5,000/100g
    env.db.commit()

    c, hdr = env.login("ANALYST")
    # Own product: Regular 12,000 (4,000/100g), Promo 7,500 (2,500/100g)
    r = c.post(
        "/api/v1/compare/products",
        json={
            "name": f"Zz{env.tag} DualState",
            "pack_size": "300g",
            "regular_price": 12000,
            "promo_price": 7500,
            "promo_type": "DISCOUNT",
        },
        headers=hdr,
    )
    assert r.status_code == 201

    data = c.get("/api/v1/compare/").json()
    ours = next(p for p in data["products"] if p["name"] == f"Zz{env.tag} DualState")

    assert ours["regular_price_per_100g"] == 4000
    assert ours["promo_price_per_100g"] == 2500
    assert ours["has_active_promo"] is True
    # 2 competitor promos undercut our regular price (DeepDiscount & MidDiscount)
    assert ours["undercut_count"] >= 2
    # Only 1 competitor promo undercuts our promotional price (DeepDiscount)
    assert ours["promo_undercut_count"] >= 1

    mine = {m["product"].split(" ", 1)[1]: m for m in ours["comparable"] if m["product"].startswith(f"Zz{env.tag}")}
    assert mine["DeepDiscount"]["regular_to_promo_gap_pct"] == -50.0
    assert mine["DeepDiscount"]["promo_to_promo_gap_pct"] == -20.0
    assert mine["DeepDiscount"]["undercuts_us"] is True
    assert mine["DeepDiscount"]["undercuts_our_promo"] is True

    assert mine["MidDiscount"]["regular_to_promo_gap_pct"] == -25.0
    assert mine["MidDiscount"]["promo_to_promo_gap_pct"] == 20.0
    assert mine["MidDiscount"]["undercuts_us"] is True
    assert mine["MidDiscount"]["undercuts_our_promo"] is False

    assert mine["Dearer"]["regular_to_promo_gap_pct"] == 25.0
    assert mine["Dearer"]["promo_to_promo_gap_pct"] == 100.0
    assert mine["Dearer"]["undercuts_us"] is False
    assert mine["Dearer"]["undercuts_our_promo"] is False


def test_strict_multi_source_validity_filters(env, monkeypatch):
    from app.services import comparison
    monkeypatch.setattr(comparison, "MAX_MATCHES", 10_000)

    now = datetime.now(timezone.utc)
    # 1. Valid Active dated promo
    env.promo("ValidDated", pack_size="300g", promo_price=8000, start_date=now - timedelta(days=2), end_date=now + timedelta(days=5))
    # 2. Future promo (must be excluded)
    env.promo("FutureDated", pack_size="300g", promo_price=5000, start_date=now + timedelta(days=2), end_date=now + timedelta(days=8))
    # 3. Expired promo (must be excluded)
    env.promo("ExpiredDated", pack_size="300g", promo_price=5000, start_date=now - timedelta(days=10), end_date=now - timedelta(days=1))
    # 4. Valid unstated dates (verified within 14 days)
    env.promo("RecentUndated", pack_size="300g", promo_price=8500, start_date=None, end_date=None, last_verified_at=now - timedelta(days=3))
    # 5. Stale unstated dates (verified 20 days ago, must be excluded)
    env.promo("StaleUndated", pack_size="300g", promo_price=5000, start_date=None, end_date=None, last_verified_at=now - timedelta(days=20))
    env.db.commit()

    c, hdr = env.login("ANALYST")
    c.post("/api/v1/compare/products", json={"name": f"Zz{env.tag} Ours", "pack_size": "300g", "regular_price": 10000}, headers=hdr)

    data = c.get("/api/v1/compare/").json()
    ours = next(p for p in data["products"] if p["name"] == f"Zz{env.tag} Ours")
    mine_names = [m["product"].split(" ", 1)[1] for m in ours["comparable"] if m["product"].startswith(f"Zz{env.tag}")]

    assert "ValidDated" in mine_names
    assert "RecentUndated" in mine_names
    assert "FutureDated" not in mine_names
    assert "ExpiredDated" not in mine_names
    assert "StaleUndated" not in mine_names


def test_multidimensional_aggregations_and_endpoints(env):
    c, hdr = env.login("ANALYST")
    # Test GET /api/v1/compare/aggregations
    r = c.get("/api/v1/compare/aggregations")
    assert r.status_code == 200
    aggs = r.json()
    assert "by_brand" in aggs
    assert "by_category" in aggs
    assert "by_retailer" in aggs
    assert "by_mechanic" in aggs
    assert "total_active_promotions" in aggs

    # Test that /api/v1/compare/ also includes aggregations
    r2 = c.get("/api/v1/compare/")
    assert r2.status_code == 200
    data = r2.json()
    assert "aggregations" in data
    assert "summary" in data
    assert "products" in data


def test_simulation_what_if_endpoint(env, monkeypatch):
    from app.services import comparison
    monkeypatch.setattr(comparison, "MAX_MATCHES", 10_000)

    # Competitor promo at 8,000 for 300g (2,666.67/100g)
    env.promo("CompA", pack_size="300g", promo_price=8000)
    env.db.commit()

    analyst, hdr = env.login("ANALYST")
    # Create an own product at 12,000 (4,000/100g)
    created = analyst.post(
        "/api/v1/compare/products",
        json={"name": f"Zz{env.tag} SimTarget", "pack_size": "300g", "regular_price": 12000},
        headers=hdr,
    ).json()

    # 1. Simulate on existing product: candidate price Rp 7,000 (undercuts competitor)
    sim_res = analyst.post(
        "/api/v1/compare/simulate",
        json={
            "product_id": created["id"],
            "candidate_promo_price": 7000,
        },
        headers=hdr,
    )
    assert sim_res.status_code == 200
    res = sim_res.json()

    assert res["simulated_product"]["candidate_effective_pack_price"] == 7000
    assert pytest.approx(res["simulated_product"]["candidate_price_per_100g"], 0.1) == 2333.33
    assert res["projected_position"]["market_position"] in ("CHEAPEST_IN_MARKET", "TOP_QUARTILE_COMPETITIVE")
    assert "impact_summary" in res

    # 2. Simulate BUY_X_GET_Y mechanics on hypothetical new product
    hypo_res = analyst.post(
        "/api/v1/compare/simulate",
        json={
            "name": "Hypothetical Wafer",
            "category": "WAFER",
            "pack_size": "200g",
            "regular_price": 10000,
            "candidate_promo_type": "BUY_X_GET_Y",
            "buy_quantity": 2,
            "free_quantity": 1,
        },
        headers=hdr,
    )
    assert hypo_res.status_code == 200
    hypo_data = hypo_res.json()
    # 10,000 * 2 / 3 = 6,666.67 per pack -> 3,333.33 / 100g
    assert pytest.approx(hypo_data["simulated_product"]["candidate_effective_pack_price"], 0.1) == 6666.67
    assert pytest.approx(hypo_data["simulated_product"]["candidate_price_per_100g"], 0.1) == 3333.33

    # 3. Permissions: VIEWER is rejected
    viewer, vhdr = env.login("VIEWER")
    assert viewer.post("/api/v1/compare/simulate", json={"regular_price": 5000, "pack_size": "300g"}).status_code == 403


def test_executive_export_and_overview_metrics(env, monkeypatch):
    from app.services import comparison
    monkeypatch.setattr(comparison, "MAX_MATCHES", 10_000)

    # Competitor promo at 8,000 for 300g (2,666.67/100g)
    env.promo("CompDiscount", pack_size="300g", promo_price=8000, discount_percentage=20)
    env.db.commit()

    analyst, hdr = env.login("ANALYST")
    analyst.post(
        "/api/v1/compare/products",
        json={"name": f"Zz{env.tag} ExecTest", "pack_size": "300g", "regular_price": 10000},
        headers=hdr,
    )

    # Test summary has executive overview metrics
    res = analyst.get("/api/v1/compare/").json()
    summary = res["summary"]
    assert "price_index_vs_market" in summary
    assert "pct_under_pressure" in summary
    assert "deepest_discount_by_category" in summary
    assert "promo_frequency" in summary

    # Test one-click executive export CSV
    r_csv = analyst.get("/api/v1/compare/export?format=csv")
    assert r_csv.status_code == 200
    assert "text/csv" in r_csv.headers["content-type"]
    assert "attachment" in r_csv.headers["content-disposition"]
    assert r_csv.content.startswith(b"\xef\xbb\xbf")
    assert b"Our Product" in r_csv.content
    assert b"Competitive Status" in r_csv.content

    # Test one-click executive export Excel (XLSX)
    r_xlsx = analyst.get("/api/v1/compare/export?format=xlsx")
    assert r_xlsx.status_code == 200
    assert "spreadsheetml" in r_xlsx.headers["content-type"]
    assert "attachment" in r_xlsx.headers["content-disposition"]
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(r_xlsx.content))
    assert "Price Comparison" in wb.sheetnames
    ws = wb["Price Comparison"]
    assert ws["A1"].value.startswith("Executive Price Comparison")

    # Viewer cannot export
    viewer, _ = env.login("VIEWER")
    assert viewer.get("/api/v1/compare/export?format=csv").status_code == 403


def test_scoped_price_comparison_and_history(env):
    c,h=env.login("ANALYST")
    product=c.post("/api/v1/compare/products",json={"name":f"Zz{env.tag} Scoped","category":"WAFER","pack_size":"100g","regular_price":10000},headers=h).json()
    retailer=c.get("/api/v1/field/options").json()["retailers"][0]
    day=datetime.now(timezone.utc).date()
    scope={"retailer_id":retailer["id"],"region":"Jakarta","starts":(day-timedelta(days=1)).isoformat(),
           "ends":(day+timedelta(days=1)).isoformat(),"regular_price":11000,"promo_price":8500}
    assert c.post(f"/api/v1/compare/products/{product['id']}/prices",json=scope,headers=h).status_code==201
    rows=c.get("/api/v1/compare/",params={"category":"WAFER","retailer":retailer["name"],"region":"JABODETABEK"}).json()["products"]
    row=next(r for r in rows if r["id"]==product["id"])
    assert row["promo_price"]==8500 and row["regular_price"]==11000
    history=c.get(f"/api/v1/compare/products/{product['id']}/history").json()
    assert history[0]["snapshot"]["regular_price"]==10000


def test_marketing_can_exclude_and_restore_a_product_match(env):
    own, headers = env.login("ANALYST")
    offer = env.promo("Comparable pack", pack_size="300g", promo_price=8000)
    env.db.commit()
    product = own.post("/api/v1/compare/products", headers=headers, json={
        "name":f"Zz{env.tag} Match", "pack_size":"300g","regular_price":12000}).json()
    path = f"/api/v1/compare/products/{product['id']}/matches"
    params = {"search":f"Zz{env.tag} Comparable pack"}
    def matches():
        rows = own.get("/api/v1/compare/",params=params).json()["products"]
        return [m for r in rows if r["id"]==product["id"] for m in r["comparable"]]
    assert matches()[0]["match_basis"] == "Category and pack size"
    for value in (True,False):
        assert own.put(path,headers=headers,json={"promotion_id":str(offer.id),"accepted":value}).status_code == 200
        if value:
            assert matches()[0]["match_basis"] == "Analyst confirmed"
        else:
            assert matches() == []
    assert own.delete(path,headers=headers).status_code == 204
    assert matches()[0]["match_basis"] == "Category and pack size"
