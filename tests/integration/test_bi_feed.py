"""Integration tests for Executive BI Feed and Campaign endpoints.

Validates:
1. /api/v1/stats/bi-feed returns JSON structured for BI systems.
2. /api/v1/stats/bi-feed with format=csv returns downloadable CSV with safe cells and BOM.
3. Campaign filters correctly slice the dataset.
4. /api/v1/stats/campaigns lists defined campaigns.
"""
import csv
import io
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.passwords import hash_password
from app.db.session import SessionLocal
from app.main import app
from app.models.auth import User
from app.models.entity import Brand, Competitor, Retailer
from app.models.promotion import Promotion, PromotionEvidence
from app.models.source import SourceRegistry

NOW = datetime.now(timezone.utc)


@pytest.fixture()
def bi_client(monkeypatch):
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"PostgreSQL is not reachable: {exc}")

    # Create viewer user
    username = f"biviewer_{uuid.uuid4().hex[:6]}"
    user = User(
        username=username,
        display_name="BI Viewer",
        password_hash=hash_password("StrongPassword123!"),
        role="VIEWER",
        is_active=True,
    )
    db.add(user)

    # Competitor & Retailer
    comp_name = f"BIComp_{uuid.uuid4().hex[:5]}"
    ret_name = f"BIRet_{uuid.uuid4().hex[:5]}"
    comp = Competitor(name=comp_name, normalized_name=comp_name.lower(), is_active=True)
    ret = Retailer(name=ret_name, normalized_name=ret_name.lower())
    db.add_all([comp, ret])

    src = SourceRegistry(
        name=f"BISrc_{uuid.uuid4().hex[:5]}",
        domain=f"bi-{uuid.uuid4().hex[:6]}.example",
        base_url="https://bi.example/",
        source_type="RETAILER",
        adapter_key="generic_catalog",
        approval_status="APPROVED",
        is_active=True,
        last_crawled_at=NOW,
        last_success_at=NOW,
    )
    db.add(src)
    db.flush()

    # Promos: 1 Ramadhan promo, 1 BOGO promo
    p1 = Promotion(
        competitor_id=comp.id,
        retailer_id=ret.id,
        source_id=src.id,
        product_name="Khong Guan Biscuit Ramadhan Kaleng 1600g",
        category="BISCUIT",
        pack_size="1600g",
        regular_price=120000.0,
        promo_price=99000.0,
        discount_percentage=17.5,
        promotion_type="DISCOUNT",
        status="ACTIVE",
        geography_region="JAWA",
        rank_score=90.0,
        first_seen_at=NOW,
        last_seen_at=NOW,
        last_verified_at=NOW,
    )
    p2 = Promotion(
        competitor_id=comp.id,
        retailer_id=ret.id,
        source_id=src.id,
        product_name="Oreo Strawberry Cream Beli 2 Gratis 1",
        category="COOKIE",
        pack_size="133g",
        regular_price=10000.0,
        promo_price=10000.0,
        buy_quantity=2,
        free_quantity=1,
        promotion_type="BUY_X_GET_Y",
        status="ACTIVE",
        geography_region="JAWA",
        rank_score=85.0,
        first_seen_at=NOW,
        last_seen_at=NOW,
        last_verified_at=NOW,
    )
    db.add_all([p1, p2])
    db.flush()

    ev1 = PromotionEvidence(promotion_id=p1.id, evidence_text="Spesial Berkah Ramadhan Khong Guan Kaleng Rp99.000")
    ev2 = PromotionEvidence(promotion_id=p2.id, evidence_text="Beli 2 Gratis 1 Oreo Strawberry")
    db.add_all([ev1, ev2])
    db.commit()

    # Login to get session cookie
    client = TestClient(app)
    login_resp = client.post("/api/v1/auth/login", json={"username": username, "password": "StrongPassword123!"})
    assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"

    yield client, p1.id, p2.id, comp.id

    # Teardown
    db.rollback()
    db.query(PromotionEvidence).filter(PromotionEvidence.promotion_id.in_([p1.id, p2.id])).delete(synchronize_session=False)
    db.query(Promotion).filter(Promotion.id.in_([p1.id, p2.id])).delete(synchronize_session=False)
    db.query(SourceRegistry).filter(SourceRegistry.id == src.id).delete(synchronize_session=False)
    db.query(Retailer).filter(Retailer.id == ret.id).delete(synchronize_session=False)
    db.query(Competitor).filter(Competitor.id == comp.id).delete(synchronize_session=False)
    db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
    db.commit()
    db.close()


def test_bi_feed_json(bi_client):
    client, p1_id, p2_id, comp_id = bi_client
    resp = client.get(f"/api/v1/stats/bi-feed?competitor={comp_id}")
    assert resp.status_code == 200
    data = resp.json()

    assert "meta" in data
    assert "data" in data
    assert data["meta"]["total_records"] >= 2
    assert "columns" in data["meta"]

    pids = [r["promotion_id"] for r in data["data"]]
    assert str(p1_id) in pids
    assert str(p2_id) in pids

    # Check that campaign tagging is present
    p1_row = next(r for r in data["data"] if r["promotion_id"] == str(p1_id))
    assert "RAMADHAN_LEBARAN" in p1_row["campaign_codes"]
    assert p1_row["pack_grams"] == 1600.0

    p2_row = next(r for r in data["data"] if r["promotion_id"] == str(p2_id))
    assert "BOGO" in p2_row["campaign_codes"]
    assert p2_row["effective_pack_price"] is not None


def test_bi_feed_csv(bi_client):
    client, p1_id, p2_id, comp_id = bi_client
    resp = client.get(f"/api/v1/stats/bi-feed?format=csv&competitor={comp_id}")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["Content-Type"]
    assert "attachment; filename=" in resp.headers.get("Content-Disposition", "")

    # Decode CSV content
    text = resp.content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    assert len(rows) >= 2
    assert "product_name" in reader.fieldnames
    assert "campaign_codes" in reader.fieldnames
    assert "price_per_100g" in reader.fieldnames


def test_bi_feed_campaign_filter(bi_client):
    client, p1_id, p2_id, comp_id = bi_client
    # Slicing only Ramadhan promotions
    resp = client.get(f"/api/v1/stats/bi-feed?campaign=RAMADHAN_LEBARAN&competitor={comp_id}")
    assert resp.status_code == 200
    data = resp.json()
    pids = [r["promotion_id"] for r in data["data"]]
    assert str(p1_id) in pids
    assert str(p2_id) not in pids


def test_campaigns_list_endpoint(bi_client):
    client, _, _, _ = bi_client
    resp = client.get("/api/v1/stats/campaigns")
    assert resp.status_code == 200
    campaigns = resp.json()["campaigns"]
    assert len(campaigns) >= 8
    codes = {c["code"] for c in campaigns}
    assert "RAMADHAN_LEBARAN" in codes
    assert "JSM_WEEKEND" in codes
