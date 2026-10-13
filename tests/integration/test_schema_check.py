"""A database that does not match the code must produce a clear message, never a bare 'Internal Server Error'."""
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.core.config import settings
from app.core.errors import setup_problem_response
from app.db.session import SessionLocal
from app.main import app
from app.models.auth import AuditLog, User
from app.services import auth as auth_service
from app.services import schema_check
from app.services.schema_check import schema_status

ROOT = Path(__file__).resolve().parents[2]
PASSWORD = "Correct-Horse-Battery-9"
OLD_REVISION = "b1c2d3e4f501"        # the release before two-factor / PRD alignment / alerts


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


def fake(monkeypatch, *, current=None, expected=("g6b7c8d9e012",), error=None):
    def current_heads(engine):
        if error:
            raise error
        return frozenset(current or [])
    monkeypatch.setattr(schema_check, "_current_heads", current_heads)
    monkeypatch.setattr(schema_check, "expected_heads", lambda: frozenset(expected))


# --------------------------------------------------------------------------- the status check itself
def test_up_to_date_database_is_ok(db):
    st = schema_status()
    assert st["ok"] and st["problem"] is None and st["current"] == st["expected"]


def test_each_problem_is_named_and_comes_with_a_fix(monkeypatch):
    fake(monkeypatch, current=[])
    st = schema_status()
    assert st["problem"] == "schema_not_set_up" and "alembic upgrade head" in st["fix"]

    fake(monkeypatch, current=[OLD_REVISION])
    st = schema_status()
    assert st["problem"] == "schema_outdated" and OLD_REVISION in st["message"] and "g6b7c8d9e012" in st["message"]
    assert "alembic upgrade head" in st["fix"] and "Back up" in st["fix"]

    fake(monkeypatch, current=["zzzz_from_a_newer_version"])
    st = schema_status()
    assert st["problem"] == "schema_newer" and "git pull" in st["fix"]

    fake(monkeypatch, error=OperationalError("x", {}, Exception("connection refused")))
    st = schema_status()
    assert st["problem"] == "database_unreachable" and "DATABASE_URL" in st["fix"]
    assert "connection refused" not in str(st)                                            # details stay in the log


def test_health_tells_the_truth(db, monkeypatch):
    c = TestClient(app)
    assert c.get("/health").json() == {"status": "ok"}
    fake(monkeypatch, current=[OLD_REVISION])
    r = c.get("/health")
    body = r.json()
    assert r.status_code == 503 and body["status"] == "error" and body["problem"] == "schema_outdated" and "alembic upgrade head" in body["fix"]
    fake(monkeypatch, error=OperationalError("x", {}, Exception("boom")))
    assert c.get("/health").status_code == 503


def test_checklist_database_row_uses_the_same_check(db, monkeypatch):
    from app.services.preflight import FAIL, run_checks
    fake(monkeypatch, current=[OLD_REVISION])
    row = {c.name: c for c in run_checks(db)}["Database"]
    assert row.status == FAIL and "alembic upgrade head" in row.fix


def test_check_schema_command_exit_codes(monkeypatch, capsys):
    import scripts.check_schema as cli
    fake(monkeypatch, current=[OLD_REVISION])
    assert cli.main() == 1
    out = capsys.readouterr().out
    assert "PROBLEM" in out and "alembic upgrade head" in out
    fake(monkeypatch, current=["g6b7c8d9e012"])
    assert cli.main() == 0 and "OK" in capsys.readouterr().out


# --------------------------------------------------------------------------- what people see
class _Req:
    def __init__(self, path, accept):
        from starlette.requests import Request
        self.r = Request({"type": "http", "method": "GET", "path": path, "headers": [(b"accept", accept.encode())], "query_string": b"", "scheme": "http",
                          "server": ("t", 80), "client": ("c", 1), "http_version": "1.1"})


def test_friendly_responses_for_browsers_and_apis():
    status = {"ok": False, "problem": "schema_outdated", "message": "The database is out of date <script>x</script>.",
              "fix": "Back up the database, then run:  alembic upgrade head   and restart the application."}
    page = setup_problem_response(_Req("/", "text/html,application/xhtml+xml").r, status)
    html = page.body.decode()
    assert page.status_code == 503 and "The database needs upgrading" in html and "<code>alembic upgrade head</code>" in html
    assert "<script>x</script>" not in html and "&lt;script&gt;" in html                       # nothing is injected
    assert "Traceback" not in html and "psycopg" not in html

    api = setup_problem_response(_Req("/api/v1/stats/", "*/*").r, status)
    assert api.status_code == 503 and b"alembic upgrade head" in api.body and b"schema_outdated" in api.body


def _login(db, role="ANALYST"):
    auth_service.ip_throttle.clear()
    name = f"sc_{uuid.uuid4().hex[:8]}"
    auth_service.create_user(db, username=name, password=PASSWORD, role=role)
    db.commit()
    c = TestClient(app, follow_redirects=False)
    assert c.post("/api/v1/auth/login", json={"username": name, "password": PASSWORD}).status_code == 200
    return c, name


def _cleanup(db, name):
    db.query(AuditLog).filter(AuditLog.username == name).delete(synchronize_session=False)
    db.query(User).filter(User.username == name).delete(synchronize_session=False)
    db.commit()


def test_database_errors_get_a_setup_message_only_when_the_schema_really_is_the_problem(db, monkeypatch):
    c, name = _login(db)
    try:
        def boom(*a, **k):
            raise ProgrammingError("select", {}, Exception('column "nope" does not exist'))
        monkeypatch.setattr("app.api.v1.endpoints.stats.live_promotion_filter", boom)

        r = c.get("/api/v1/stats/")                                           # schema is fine: this is a genuine bug -> stays a 500
        assert r.status_code == 500 and r.json() == {"detail": "Internal Server Error"}

        fake(monkeypatch, current=[OLD_REVISION])                             # schema outdated: same error now explains itself
        r = c.get("/api/v1/stats/")
        assert r.status_code == 503 and "alembic upgrade head" in r.json()["detail"] and "nope" not in r.text
    finally:
        _cleanup(db, name)


def test_a_failing_session_lookup_does_not_lock_people_out_of_the_login_page(db, monkeypatch):
    def broken(*a, **k):
        raise ProgrammingError("select", {}, Exception("column users.totp_secret_enc does not exist"))
    monkeypatch.setattr("app.core.deps.resolve_session", broken)
    c = TestClient(app, follow_redirects=False)
    c.cookies.set("ci_session", "a-cookie-from-an-earlier-version")
    r = c.get("/login")
    assert r.status_code == 200 and "Sign in" in r.text
    r = c.get("/")
    assert r.status_code == 303 and r.headers["location"] == "/login"
    assert c.get("/api/v1/stats/").status_code == 401                         # treated as signed out, not a crash


# --------------------------------------------------------------------------- the real incident, end to end
@pytest.fixture()
def old_database(monkeypatch):
    """A real database left at the previous release's schema, with a user who is logged in (the incident)."""
    base = make_url(settings.DATABASE_URL_ADMIN)
    name = f"zz_old_{uuid.uuid4().hex[:8]}"
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
    except Exception as exc:
        pytest.skip(f"cannot create a scratch database here: {exc}")
    url = base.set(database=name)
    env = {**os.environ, "DATABASE_URL": url.render_as_string(hide_password=False), "DATABASE_URL_ADMIN": url.render_as_string(hide_password=False),
           "PYTHONPATH": str(ROOT)}
    done = subprocess.run([sys.executable, "-m", "alembic", "upgrade", OLD_REVISION], cwd=ROOT, env=env, capture_output=True, text=True)
    if done.returncode != 0:
        pytest.skip(f"could not build the old schema: {done.stderr[-200:]}")
    engine = create_engine(url)
    import hashlib
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO competitor_intel.users (id, username, password_hash, role, is_active, must_change_password, failed_login_count, "
                          "password_changed_at, created_at, updated_at) VALUES (gen_random_uuid(), 'olduser', 'x', 'ADMIN', true, false, 0, now(), now(), now())"))
        conn.execute(text("INSERT INTO competitor_intel.user_sessions (id, user_id, token_hash, csrf_token, created_at, last_seen_at, expires_at) "
                          "SELECT gen_random_uuid(), id, :h, 'c', now(), now(), now() + interval '8 hours' FROM competitor_intel.users WHERE username = 'olduser'"),
                     {"h": hashlib.sha256(b"oldcookie").hexdigest()})
    from app.db import session as session_module
    original_bind = SessionLocal.kw.get("bind")
    monkeypatch.setattr(session_module, "engine", engine)
    SessionLocal.configure(bind=engine)
    yield engine
    SessionLocal.configure(bind=original_bind)
    engine.dispose()
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    admin.dispose()


def test_the_exact_incident_now_explains_itself(old_database):
    """Old database + a browser still holding a login cookie: this used to be a bare 'Internal Server Error' on / and /login."""
    c = TestClient(app, follow_redirects=False)
    c.cookies.set("ci_session", "oldcookie")

    login_page = c.get("/login")
    assert login_page.status_code == 200 and "Sign in" in login_page.text                 # still reachable
    assert c.get("/").status_code == 303                                                  # sent to sign in, not an error

    health = c.get("/health")
    assert health.status_code == 503 and health.json()["problem"] == "schema_outdated"
    assert "alembic upgrade head" in health.json()["fix"] and OLD_REVISION in health.json()["detail"]

    attempt = c.post("/api/v1/auth/login", json={"username": "olduser", "password": "whatever-it-is"})
    assert attempt.status_code == 503
    detail = attempt.json()["detail"]
    assert "out of date" in detail and "alembic upgrade head" in detail and "totp_secret_enc" not in attempt.text   # clear, and no internals
