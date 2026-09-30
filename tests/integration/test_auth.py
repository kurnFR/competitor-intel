"""Login, session, CSRF, role and lockout behaviour against PostgreSQL."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.auth import AuditLog, User, UserSession
from app.services import auth as auth_service

PASSWORD = "Correct-Horse-Battery-9"


@pytest.fixture()
def env():
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"PostgreSQL is not reachable: {exc}")
    from app.main import app
    auth_service.ip_throttle.clear()
    created = []

    def make(role="VIEWER", must_change=False, password=PASSWORD):
        name = f"t_{role.lower()}_{uuid.uuid4().hex[:8]}"
        auth_service.create_user(db, username=name, password=password, role=role, must_change_password=must_change)
        db.commit()
        created.append(name)
        return name

    def client():
        return TestClient(app, follow_redirects=False)

    def login(c, name, password=PASSWORD):
        r = c.post("/api/v1/auth/login", json={"username": name, "password": password})
        return r

    yield type("Env", (), {"db": db, "make": staticmethod(make), "client": staticmethod(client), "login": staticmethod(login)})
    db.rollback()
    for name in created:
        db.query(AuditLog).filter(AuditLog.username == name).delete(synchronize_session=False)
        db.query(User).filter(User.username == name).delete(synchronize_session=False)
    db.commit()
    db.close()
    auth_service.ip_throttle.clear()


def test_api_and_pages_require_login(env):
    c = env.client()
    for path in ("/api/v1/promotions/top10", "/api/v1/stats/", "/api/v1/pipeline/status", "/api/v1/auth/users"):
        assert c.get(path).status_code == 401, path
    r = c.get("/")
    assert r.status_code == 303 and r.headers["location"] == "/login"
    assert c.get("/login").status_code == 200
    assert c.get("/health").json() == {"status": "ok"}


def test_login_cookie_flags_and_hashed_token(env):
    name = env.make("VIEWER")
    c = env.client()
    r = env.login(c, name)
    assert r.status_code == 200 and r.json()["user"]["username"] == name
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "path=/" in cookie
    raw = c.cookies.get("ci_session")
    env.db.expire_all()
    hashes = [s.token_hash for s in env.db.query(UserSession).all()]
    assert raw not in hashes and auth_service._hash_token(raw) in hashes  # only the hash is stored
    assert c.get("/api/v1/promotions/top10").status_code == 200
    assert c.get("/").status_code == 200


def test_generic_error_for_unknown_user_and_bad_password(env):
    name = env.make("VIEWER")
    c = env.client()
    a = env.login(c, name, "wrong-password-123")
    b = env.login(c, "no_such_user_xyz", "wrong-password-123")
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


def test_account_lockout_after_repeated_failures(env):
    name = env.make("VIEWER")
    c = env.client()
    for _ in range(settings.LOGIN_MAX_FAILURES):
        assert env.login(c, name, "bad-password-000").status_code == 401
    assert env.login(c, name).status_code == 423          # correct password, but locked
    user = env.db.query(User).filter(User.username == name).one()
    env.db.refresh(user)
    user.locked_until = datetime.now(timezone.utc) - timedelta(seconds=1)  # lock expires
    env.db.commit()
    auth_service.ip_throttle.clear()
    assert env.login(c, name).status_code == 200


def test_ip_throttle_blocks_password_guessing(env):
    c = env.client()
    for i in range(settings.LOGIN_IP_MAX_FAILURES):
        env.login(c, f"ghost_{i}", "bad-password-000")
    assert env.login(c, "ghost_final", "bad-password-000").status_code == 429


def test_csrf_required_for_state_changes(env):
    admin = env.make("ADMIN")
    c = env.client()
    csrf = env.login(c, admin).json()["csrf_token"]
    body = {"username": f"new_{uuid.uuid4().hex[:6]}", "password": "Another-Strong-Pass-1", "role": "VIEWER"}
    assert c.post("/api/v1/auth/users", json=body).status_code == 403                                   # no token
    assert c.post("/api/v1/auth/users", json=body, headers={"X-CSRF-Token": "wrong"}).status_code == 403
    r = c.post("/api/v1/auth/users", json=body, headers={"X-CSRF-Token": csrf})
    assert r.status_code == 201 and r.json()["must_change_password"] is True
    env.db.query(User).filter(User.username == body["username"]).delete()
    env.db.commit()


def test_roles_are_enforced(env):
    viewer, analyst = env.make("VIEWER"), env.make("ANALYST")
    for name, expected_admin in ((viewer, 403), (analyst, 403)):
        c = env.client()
        csrf = env.login(c, name).json()["csrf_token"]
        assert c.get("/api/v1/auth/users").status_code == expected_admin
        assert c.get("/api/v1/auth/audit").status_code == 403
        assert c.post("/api/v1/pipeline/run", headers={"X-CSRF-Token": csrf}).status_code == 403
    c = env.client()
    env.login(c, viewer)
    assert c.get("/admin").status_code == 303  # page redirects away from admin-only pages


def test_admin_can_start_scan_with_session_or_api_key(env, monkeypatch):
    import app.main as main
    monkeypatch.setattr(main, "_run_pipeline_job", lambda: None)
    main.pipeline_state.update(status="idle")
    admin = env.make("ADMIN")
    c = env.client()
    csrf = env.login(c, admin).json()["csrf_token"]
    assert c.post("/api/v1/pipeline/run", headers={"X-CSRF-Token": csrf}).status_code == 202

    main.pipeline_state.update(status="idle")
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "automation-key")
    anon = env.client()
    assert anon.post("/api/v1/pipeline/run", headers={"X-API-Key": "nope"}).status_code == 401
    assert anon.post("/api/v1/pipeline/run", headers={"X-API-Key": "automation-key"}).status_code == 202
    assert anon.post("/api/v1/pipeline/run").status_code == 401
    main.pipeline_state.update(status="idle")


def test_forced_password_change_flow(env):
    name = env.make("VIEWER", must_change=True)
    c = env.client()
    csrf = env.login(c, name).json()["csrf_token"]
    r = c.get("/api/v1/promotions/top10")
    assert r.status_code == 403 and "PASSWORD_CHANGE_REQUIRED" in r.text
    assert c.get("/").headers["location"] == "/account"
    other = env.client()  # second session for the same user
    env.login(other, name)

    hdr = {"X-CSRF-Token": csrf}
    assert c.post("/api/v1/auth/change-password", headers=hdr, json={"current_password": "wrong", "new_password": "Brand-New-Password-7"}).status_code == 400
    assert c.post("/api/v1/auth/change-password", headers=hdr, json={"current_password": PASSWORD, "new_password": "short"}).status_code == 422
    assert c.post("/api/v1/auth/change-password", headers=hdr, json={"current_password": PASSWORD, "new_password": PASSWORD}).status_code == 422
    assert c.post("/api/v1/auth/change-password", headers=hdr, json={"current_password": PASSWORD, "new_password": "Brand-New-Password-7"}).status_code == 204
    assert c.get("/api/v1/promotions/top10").status_code == 200        # this session survives
    assert other.get("/api/v1/promotions/top10").status_code == 401    # other sessions are revoked
    assert env.login(env.client(), name).status_code == 401            # old password no longer works
    assert env.login(env.client(), name, "Brand-New-Password-7").status_code == 200


def test_logout_revokes_session(env):
    name = env.make("VIEWER")
    c = env.client()
    csrf = env.login(c, name).json()["csrf_token"]
    token = c.cookies.get("ci_session")
    assert c.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 204
    replay = env.client()
    replay.cookies.set("ci_session", token)
    assert replay.get("/api/v1/promotions/top10").status_code == 401


def test_session_expiry_absolute_and_idle(env):
    name = env.make("VIEWER")
    c = env.client()
    env.login(c, name)
    session = env.db.query(UserSession).join(User).filter(User.username == name).one()
    session.last_seen_at = datetime.now(timezone.utc) - timedelta(minutes=settings.SESSION_IDLE_MINUTES + 5)
    env.db.commit()
    assert c.get("/api/v1/promotions/top10").status_code == 401       # idle timeout

    c2 = env.client()
    env.login(c2, name)
    env.db.expire_all()
    s2 = env.db.query(UserSession).join(User).filter(User.username == name, UserSession.revoked_at.is_(None)).order_by(UserSession.created_at.desc()).first()
    s2.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    env.db.commit()
    assert c2.get("/api/v1/promotions/top10").status_code == 401      # absolute timeout


def test_deactivating_user_kills_sessions_and_last_admin_is_protected(env):
    admin, victim = env.make("ADMIN"), env.make("VIEWER")
    vc, ac = env.client(), env.client()
    env.login(vc, victim)
    csrf = env.login(ac, admin).json()["csrf_token"]
    hdr = {"X-CSRF-Token": csrf}
    victim_id = ac.get("/api/v1/auth/users").json()
    victim_id = next(u["id"] for u in victim_id if u["username"] == victim)
    assert ac.patch(f"/api/v1/auth/users/{victim_id}", json={"is_active": False}, headers=hdr).status_code == 200
    assert vc.get("/api/v1/promotions/top10").status_code == 401
    assert env.login(env.client(), victim).status_code == 401

    my_id = next(u["id"] for u in ac.get("/api/v1/auth/users").json() if u["username"] == admin)
    assert ac.patch(f"/api/v1/auth/users/{my_id}", json={"is_active": False}, headers=hdr).status_code == 409


def test_audit_log_records_events_without_passwords(env):
    name = env.make("VIEWER")
    c = env.client()
    env.login(c, name, "bad-password-000")
    env.login(c, name)
    rows = env.db.query(AuditLog).filter(AuditLog.username == name).all()
    assert {"login_failed", "login"} <= {r.action for r in rows}
    logged = " ".join(str(r.detail) for r in rows)
    assert PASSWORD not in logged and "bad-password-000" not in logged      # secrets are never written to the log


def test_security_headers_present(env):
    r = env.client().get("/login")
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers["cache-control"] == "no-store"


def test_all_pages_render_for_the_right_roles(env):
    admin, viewer = env.make("ADMIN"), env.make("VIEWER")
    a, v = env.client(), env.client()
    env.login(a, admin)
    env.login(v, viewer)
    for path in ("/", "/insights", "/compare", "/review", "/admin", "/account"):
        r = a.get(path)
        assert r.status_code == 200 and "text/html" in r.headers["content-type"], path
    assert 'id="scan-button"' in a.get("/").text and "/admin" in a.get("/").text
    assert 'id="scan-button"' not in v.get("/").text                    # viewers do not see admin controls
    assert v.get("/insights").status_code == 200
    assert v.get("/review").status_code == 303 and v.get("/admin").status_code == 303


def test_sources_admin_api(env, monkeypatch):
    from app.models.source import SourceRegistry
    monkeypatch.setattr("app.api.v1.endpoints.sources.validate_source_url",
                        lambda url: __import__("app.services.sources", fromlist=["x"]).validate_source_url(url, resolve=False))
    admin, viewer = env.make("ADMIN"), env.make("VIEWER")
    v, a = env.client(), env.client()
    env.login(v, viewer)
    assert v.get("/api/v1/sources/").status_code == 403
    csrf = env.login(a, admin).json()["csrf_token"]
    hdr = {"X-CSRF-Token": csrf}
    tag = uuid.uuid4().hex[:8]
    url = f"https://93.184.216.34/promo-{tag}"
    try:
        r = a.post("/api/v1/sources/", json={"name": f"Test {tag}", "base_url": url, "source_type": "RETAILER"}, headers=hdr)
        assert r.status_code == 201 and r.json()["health"] == "NEVER_SCANNED"
        sid = r.json()["id"]
        assert a.post("/api/v1/sources/", json={"name": "Dup", "base_url": url}, headers=hdr).status_code == 409
        for bad in ("http://169.254.169.254/x", "http://localhost/x", "ftp://x.example.com/a"):
            assert a.post("/api/v1/sources/", json={"name": "Bad", "base_url": bad}, headers=hdr).status_code == 422
        assert a.post("/api/v1/sources/", json={"name": "T", "base_url": url + "2", "source_type": "WEIRD"}, headers=hdr).status_code == 422
        off = a.patch(f"/api/v1/sources/{sid}", json={"is_active": False}, headers=hdr)
        assert off.status_code == 200 and off.json()["health"] == "DISABLED"
        assert a.patch(f"/api/v1/sources/{sid}", json={"reliability_score": 5}, headers=hdr).status_code == 422
    finally:
        env.db.query(SourceRegistry).filter(SourceRegistry.base_url.like(f"%promo-{tag}%")).delete(synchronize_session=False)
        env.db.commit()
