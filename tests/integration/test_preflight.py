"""Setup self-check: each finding, no secret leakage, permissions, CLI exit code."""
import json
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.config import settings
from app.db.session import SessionLocal
from app.main import app
from app.models.auth import AuditLog, User
from app.models.scan_run import ScanRun
from app.models.source import SourceRegistry
from app.services import auth as auth_service
from app.services import preflight
from app.services.preflight import FAIL, INFO, PASS, WARN, as_dict, run_checks

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


def test_every_check_reports_and_none_crash(db):
    checks = run_checks(db)
    names = [c.name for c in checks]
    assert {"Database", "Environment", "HTTPS cookies", "SECRET_KEY (two-factor)", "Administrator accounts", "Crawler etiquette",
            "LLM", "Websites to scan", "Scans", "Promotions", "Review queue", "Optional features"} <= set(names)
    assert all(c.status in (PASS, WARN, FAIL, INFO) and c.detail for c in checks)
    assert by_name(checks)["Database"].status == PASS            # the test database is migrated to head


def test_secret_values_are_never_shown(db, monkeypatch):
    monkeypatch.setattr(settings, "SECRET_KEY", "super-secret-key-value-0123456789abcdefghij")
    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-llm-secret-token-abc123")
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "automation-secret-key-abcdefghijklmnop")
    blob = json.dumps(as_dict(run_checks(db)))
    for secret in ("super-secret-key-value", "sk-llm-secret-token", "automation-secret-key", settings.DATABASE_URL):
        assert secret not in blob


def test_configuration_findings(db, monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "SESSION_COOKIE_SECURE", False)
    monkeypatch.setattr(settings, "CRAWLER_RESPECT_ROBOTS", False)
    monkeypatch.setattr(settings, "SECRET_KEY", "")
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "short")
    c = by_name(run_checks(db))
    assert c["HTTPS cookies"].status == FAIL and "HTTPS" in c["HTTPS cookies"].fix
    assert c["Crawler etiquette"].status == FAIL
    assert c["SECRET_KEY (two-factor)"].status == WARN and "token_urlsafe" in c["SECRET_KEY (two-factor)"].fix
    assert c["Automation API key"].status == WARN
    assert c["Environment"].status == PASS

    monkeypatch.setattr(settings, "SESSION_COOKIE_SECURE", None)
    monkeypatch.setattr(settings, "CRAWLER_RESPECT_ROBOTS", True)
    monkeypatch.setattr(settings, "CRAWLER_USER_AGENT", "CompetitorIntelBot/1.0")
    assert by_name(run_checks(db))["Crawler etiquette"].status == WARN                       # no contact details
    monkeypatch.setattr(settings, "CRAWLER_USER_AGENT", "CompetitorIntelBot/1.0 (+https://example.org/bot; ops@example.org)")
    assert by_name(run_checks(db))["Crawler etiquette"].status == PASS
    monkeypatch.setattr(settings, "SECRET_KEY", "a" * 40)
    assert by_name(run_checks(db))["SECRET_KEY (two-factor)"].status == PASS


def test_no_administrator_is_a_failure(db, monkeypatch):
    monkeypatch.setattr(preflight, "count_active_admins", lambda session: 0)
    c = by_name(run_checks(db))["Administrator accounts"]
    assert c.status == FAIL and "create_user" in c.fix


def test_sources_and_sample_data_findings(db):
    tag = uuid.uuid4().hex[:6]
    s = SourceRegistry(name=f"Test source {tag}", domain=f"x-{tag}.example", base_url=f"https://x-{tag}.example/", source_type="RETAILER",
                       adapter_key="generic_catalog", approval_status="APPROVED", is_active=True)
    cand = SourceRegistry(name=f"Candidate {tag}", domain=f"c-{tag}.com", base_url=f"https://c-{tag}.com/", source_type="RETAILER",
                          adapter_key="generic_catalog", approval_status="CANDIDATE", is_active=False)
    db.add_all([s, cand])
    db.commit()
    try:
        checks = by_name(run_checks(db))
        assert checks["Sample/test data"].status == WARN and "test data" in checks["Sample/test data"].detail
        assert checks["Websites awaiting approval"].status == INFO
    finally:
        db.query(SourceRegistry).filter(SourceRegistry.id.in_([s.id, cand.id])).delete(synchronize_session=False)
        db.commit()


@pytest.mark.parametrize("status,age_days,expected", [("FAILED", 0, FAIL), ("PARTIAL", 0, WARN), ("COMPLETED", 0, PASS), ("COMPLETED", 5, WARN)])
def test_last_scan_findings(db, monkeypatch, status, age_days, expected):
    run = ScanRun(started_at=datetime.now(timezone.utc) - timedelta(days=age_days), trigger="CLI", triggered_by="x", status=status,
                  error="boom" if status == "FAILED" else None, summary={"documents": 3, "observations": 7, "rejected": 1})
    monkeypatch.setattr(preflight, "latest_scan", lambda session: run)      # not saved: independent of other rows in the database
    c = by_name(run_checks(db))["Scans"]
    assert c.status == expected
    if status == "COMPLETED" and age_days == 0:
        assert "3 page(s)" in c.detail and "7 promotion(s)" in c.detail


def test_no_scan_yet_is_flagged(db, monkeypatch):
    monkeypatch.setattr(preflight, "latest_scan", lambda session: None)
    c = by_name(run_checks(db))["Scans"]
    assert c.status == WARN and "No scan has run yet" in c.detail


def test_llm_connection_test(db, monkeypatch):
    monkeypatch.setattr(settings, "LLM_BASE_URL", "http://llm.test/v1")
    assert by_name(run_checks(db))["LLM"].status == INFO                                       # not tested unless asked

    def fake_get(url, **kw):
        fake_get.seen = (url, kw)
        return httpx.Response(fake_get.code, request=httpx.Request("GET", url))
    monkeypatch.setattr(httpx, "get", fake_get)
    for code, expected in ((200, PASS), (401, FAIL), (500, WARN)):
        fake_get.code = code
        assert by_name(run_checks(db, check_llm=True))["LLM"].status == expected
    assert fake_get.seen[0] == "http://llm.test/v1/models"

    def down(url, **kw):
        raise httpx.ConnectError("refused")
    monkeypatch.setattr(httpx, "get", down)
    c = by_name(run_checks(db, check_llm=True))["LLM"]
    assert c.status == FAIL and "ConnectError" in c.detail


def test_a_crashing_check_becomes_a_finding_not_an_error(db, monkeypatch):
    def boom(session):
        raise RuntimeError("nope")
    monkeypatch.setattr(preflight, "_review", boom)
    checks = run_checks(db)
    broken = [c for c in checks if "itself failed" in c.detail]
    assert broken and broken[0].status == FAIL
    assert len(checks) >= 12                                      # the other checks still ran


def test_endpoint_is_admin_only_and_page_shows_checklist(db):
    auth_service.ip_throttle.clear()
    tag = uuid.uuid4().hex[:8]
    names = {r: f"pf_{r.lower()}_{tag}" for r in ("VIEWER", "ADMIN")}
    for role, name in names.items():
        auth_service.create_user(db, username=name, password=PASSWORD, role=role)
    db.commit()
    try:
        def login(role):
            c = TestClient(app, follow_redirects=False)
            assert c.post("/api/v1/auth/login", json={"username": names[role], "password": PASSWORD}).status_code == 200
            return c
        assert TestClient(app).get("/api/v1/system/check").status_code == 401
        assert login("VIEWER").get("/api/v1/system/check").status_code == 403
        admin = login("ADMIN")
        data = admin.get("/api/v1/system/check").json()
        assert set(data["summary"]) == {"PASS", "WARN", "FAIL", "INFO", "ready"} and len(data["checks"]) >= 12
        assert {"name", "status", "detail", "fix"} <= set(data["checks"][0])
        assert "Setup checklist" in admin.get("/admin").text
    finally:
        for name in names.values():
            db.query(AuditLog).filter(AuditLog.username == name).delete(synchronize_session=False)
            db.query(User).filter(User.username == name).delete(synchronize_session=False)
        db.commit()


def test_cli_exit_code_reflects_failures(monkeypatch, capsys):
    import scripts.preflight as cli
    ok = [preflight.Check("A", PASS, "fine"), preflight.Check("B", WARN, "meh", "do x")]
    monkeypatch.setattr(cli, "run_checks", lambda db, check_llm=False: ok)
    monkeypatch.setattr("sys.argv", ["preflight"])
    assert cli.main() == 0
    assert "Ready to use" in capsys.readouterr().out
    monkeypatch.setattr(cli, "run_checks", lambda db, check_llm=False: ok + [preflight.Check("C", FAIL, "broken", "fix it")])
    assert cli.main() == 1
    out = capsys.readouterr().out
    assert "[FAIL] C: broken" in out and "-> fix it" in out and "Fix the failures above first" in out
