import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.session import SessionLocal
from app.main import app
from app.models.auth import AuditLog, User
from app.services import auth as auth_service

PASSWORD = "Correct-Horse-Battery-9"


@pytest.fixture()
def client():
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"PostgreSQL is not reachable: {exc}")
    auth_service.ip_throttle.clear()
    name = f"api_{uuid.uuid4().hex[:8]}"
    auth_service.create_user(db, username=name, password=PASSWORD, role="ANALYST")
    db.commit()
    c = TestClient(app)
    assert c.post("/api/v1/auth/login", json={"username": name, "password": PASSWORD}).status_code == 200
    yield c
    db.query(AuditLog).filter(AuditLog.username == name).delete(synchronize_session=False)
    db.query(User).filter(User.username == name).delete(synchronize_session=False)
    db.commit()
    db.close()


def test_health():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_endpoints_reject_anonymous_users():
    anon = TestClient(app)
    assert anon.get("/api/v1/stats/").status_code == 401
    assert anon.get("/api/v1/promotions/top10").status_code == 401
    assert anon.get("/api/v1/promotions/export").status_code == 401


def test_stats(client):
    data = client.get("/api/v1/stats/").json()
    assert "active_promotions" in data
    assert "competitors_tracked" in data


def test_top10(client):
    data = client.get("/api/v1/promotions/top10").json()
    assert "promotions" in data
    assert len(data["promotions"]) <= 10
    if data["promotions"]:
        first = data["promotions"][0]
        assert first["rank"] == 1
        assert "rank_score" in first
        assert "product_name" in first
