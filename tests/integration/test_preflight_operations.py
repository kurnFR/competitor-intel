"""Setup checklist: failure-alert channel, disk space/retention, and the recent-alerts endpoint."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.config import settings
from app.db.session import SessionLocal
from app.main import app
from app.models.auth import AuditLog, User
from app.services import auth as auth_service
from app.services.preflight import PASS, WARN, run_checks

PASSWORD = "Correct-Horse-Battery-9"


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


def by_name(checks):
    return {c.name: c for c in checks}


def test_alert_channel_and_disk_checks(db, monkeypatch, tmp_path):
    from app.services import notify
    monkeypatch.setattr(notify, "any_channel_configured", lambda: False)
    c = by_name(run_checks(db))["Failure alerts"]
    assert c.status == WARN and "nobody will be told" in c.detail and "DIGEST_WEBHOOK_URL" in c.fix

    monkeypatch.setattr(notify, "any_channel_configured", lambda: True)
    monkeypatch.setattr(notify, "email_configured", lambda: False)
    monkeypatch.setattr(notify, "webhook_configured", lambda: True)
    c = by_name(run_checks(db))["Failure alerts"]
    assert c.status in (PASS, WARN) and (c.status == WARN or "chat webhook" in c.detail)

    monkeypatch.setenv("RAW_DOCUMENT_STORAGE_PATH", str(tmp_path / "raw"))
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "f.bin").write_bytes(b"x" * 2048)
    monkeypatch.setattr(settings, "RETENTION_ENABLED", False)
    d = by_name(run_checks(db))["Disk space"]
    assert d.status == WARN and "retention is OFF" in d.detail.lower().replace("data ", "") or "OFF" in d.detail
    monkeypatch.setattr(settings, "RETENTION_ENABLED", True)
    d = by_name(run_checks(db))["Disk space"]
    assert d.status in (PASS, WARN) and "trimmed daily" in d.detail


def test_recent_alerts_endpoint_is_admin_only(db):
    import uuid as _uuid
    from app.models.alert import AlertEvent
    auth_service.ip_throttle.clear()
    tag = _uuid.uuid4().hex[:8]
    names = {r: f"al_{r.lower()}_{tag}" for r in ("VIEWER", "ADMIN")}
    for role, name in names.items():
        auth_service.create_user(db, username=name, password=PASSWORD, role=role)
    db.add(AlertEvent(fingerprint=f"endpoint-{tag}", kind="SCAN_FAILED", title="Scan failed", body="boom", subject_id=f"x-{tag}"))
    db.commit()
    try:
        def login(role):
            c = TestClient(app, follow_redirects=False)
            assert c.post("/api/v1/auth/login", json={"username": names[role], "password": PASSWORD}).status_code == 200
            return c
        assert TestClient(app).get("/api/v1/system/alerts").status_code == 401
        assert login("VIEWER").get("/api/v1/system/alerts").status_code == 403
        rows = login("ADMIN").get("/api/v1/system/alerts?limit=100").json()
        mine = [r for r in rows if r["title"] == "Scan failed" and r["body"] == "boom"]
        assert mine and set(mine[0]) >= {"kind", "title", "body", "created_at", "delivered", "delivery", "attempts", "last_error", "resolved_at"}
    finally:
        db.query(AlertEvent).filter(AlertEvent.fingerprint == f"endpoint-{tag}").delete(synchronize_session=False)
        for name in names.values():
            db.query(AuditLog).filter(AuditLog.username == name).delete(synchronize_session=False)
            db.query(User).filter(User.username == name).delete(synchronize_session=False)
        db.commit()
