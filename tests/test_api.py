import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_stats():
    response = client.get("/api/v1/stats/")
    assert response.status_code == 200
    data = response.json()
    assert "active_promotions" in data
    assert "competitors_tracked" in data


def test_top10():
    response = client.get("/api/v1/promotions/top10")
    assert response.status_code == 200
    data = response.json()
    assert "promotions" in data
    assert len(data["promotions"]) <= 10
    if data["promotions"]:
        first = data["promotions"][0]
        assert first["rank"] == 1
        assert "rank_score" in first
        assert "product_name" in first
