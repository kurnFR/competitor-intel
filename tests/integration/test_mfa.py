"""Two-factor (TOTP) login."""
import re
import time
import uuid

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core import crypto
from app.core.config import settings
from app.db.session import SessionLocal
from app.main import app
from app.models.auth import AuditLog, User
from app.services import auth as auth_service
from app.services import mfa as mfa_service

PASSWORD = "Correct-Horse-Battery-9"


@pytest.fixture()
def env(monkeypatch):
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"PostgreSQL is not reachable: {exc}")
    monkeypatch.setattr(settings, "SECRET_KEY", "unit-test-secret-key-0123456789abcdef")
    auth_service.ip_throttle.clear()
    created = []

    def make(role="VIEWER"):
        name = f"mfa_{role.lower()}_{uuid.uuid4().hex[:8]}"
        auth_service.create_user(db, username=name, password=PASSWORD, role=role)
        db.commit()
        created.append(name)
        return name

    def client():
        return TestClient(app, follow_redirects=False)

    def login(c, name, password=PASSWORD):
        return c.post("/api/v1/auth/login", json={"username": name, "password": password})

    def enroll(name):
        """Log in, turn 2FA on, return (secret, recovery_codes)."""
        c = client()
        csrf = login(c, name).json()["csrf_token"]
        hdr = {"X-CSRF-Token": csrf}
        setup = c.post("/api/v1/auth/mfa/setup", headers=hdr)
        assert setup.status_code == 200
        secret = setup.json()["secret"]
        r = c.post("/api/v1/auth/mfa/enable", json={"code": pyotp.TOTP(secret).now()}, headers=hdr)
        assert r.status_code == 200
        return secret, r.json()["recovery_codes"]

    yield type("Env", (), dict(db=db, make=staticmethod(make), client=staticmethod(client), login=staticmethod(login),
                               enroll=staticmethod(enroll)))
    db.rollback()
    for name in created:
        db.query(AuditLog).filter(AuditLog.username == name).delete(synchronize_session=False)
        db.query(User).filter(User.username == name).delete(synchronize_session=False)
    db.commit()
    db.close()
    auth_service.ip_throttle.clear()


def next_window_code(secret):
    """A valid code for the next 30-second window (accepted: +-1 step), standing in for 'wait 30 seconds'."""
    return pyotp.TOTP(secret).at((int(time.time()) // 30 + 1) * 30)


def test_enrolment_returns_qr_and_recovery_codes_and_needs_a_correct_code(env):
    name = env.make()
    c = env.client()
    csrf = env.login(c, name).json()["csrf_token"]
    hdr = {"X-CSRF-Token": csrf}
    setup = c.post("/api/v1/auth/mfa/setup", headers=hdr).json()
    assert setup["otpauth_uri"].startswith("otpauth://totp/") and name in setup["otpauth_uri"]
    assert setup["qr"].startswith("data:image/svg+xml")
    assert c.post("/api/v1/auth/mfa/enable", json={"code": "000000"}, headers=hdr).status_code == 400
    assert c.post("/api/v1/auth/mfa/enable", json={"code": "abc"}, headers=hdr).status_code == 400
    r = c.post("/api/v1/auth/mfa/enable", json={"code": pyotp.TOTP(setup["secret"]).now()}, headers=hdr)
    codes = r.json()["recovery_codes"]
    assert len(codes) == 10 and len(set(codes)) == 10 and re.fullmatch(r"[0-9a-f]{4}(-[0-9a-f]{4}){2}", codes[0])
    assert c.post("/api/v1/auth/mfa/setup", headers=hdr).status_code == 409           # already on
    env.db.expire_all()
    user = env.db.query(User).filter(User.username == name).one()
    assert user.totp_enabled and setup["secret"] not in user.totp_secret_enc          # stored encrypted
    assert codes[0] not in str(user.recovery_hashes)                                   # stored hashed


def test_login_with_2fa_needs_second_step(env):
    name = env.make()
    secret, _ = env.enroll(name)
    c = env.client()
    r = env.login(c, name)
    body = r.json()
    assert r.status_code == 200 and body["mfa_required"] is True and body["user"] is None and body["csrf_token"] is None
    assert "set-cookie" not in r.headers                                             # no session yet
    assert c.get("/api/v1/promotions/top10").status_code == 401

    # wrong code, garbage challenge, and a challenge signed with another key are all refused
    assert c.post("/api/v1/auth/login/mfa", json={"challenge": body["challenge"], "code": "123456"}).status_code == 401
    assert c.post("/api/v1/auth/login/mfa", json={"challenge": "junk", "code": pyotp.TOTP(secret).now()}).status_code == 401
    assert c.get("/api/v1/promotions/top10").status_code == 401

    same_window = c.post("/api/v1/auth/login/mfa", json={"challenge": body["challenge"], "code": pyotp.TOTP(secret).now()})
    assert same_window.status_code == 401                            # enrolment already used this window's code
    ok = c.post("/api/v1/auth/login/mfa", json={"challenge": body["challenge"], "code": next_window_code(secret)})
    assert ok.status_code == 200 and ok.json()["user"]["username"] == name and ok.json()["csrf_token"]
    assert "httponly" in ok.headers["set-cookie"].lower()
    assert c.get("/api/v1/promotions/top10").status_code == 200


def test_a_code_cannot_be_used_twice(env):
    name = env.make()
    secret, _ = env.enroll(name)                     # enrolment consumed the current step
    env.db.expire_all()
    used = env.db.query(User).filter(User.username == name).one().totp_last_step
    c = env.client()
    challenge = env.login(c, name).json()["challenge"]
    replay = pyotp.TOTP(secret).at(used * 30)        # the very code accepted at enrolment
    assert c.post("/api/v1/auth/login/mfa", json={"challenge": challenge, "code": replay}).status_code == 401
    fresh = pyotp.TOTP(secret).at((used + 1) * 30)   # next window
    assert c.post("/api/v1/auth/login/mfa", json={"challenge": challenge, "code": fresh}).status_code == 200


def test_challenge_expires(env, monkeypatch):
    name = env.make()
    secret, _ = env.enroll(name)
    c = env.client()
    challenge = env.login(c, name).json()["challenge"]
    real = time.time
    monkeypatch.setattr(time, "time", lambda: real() + settings.MFA_CHALLENGE_SECONDS + 5)
    assert crypto.verify_challenge(challenge) is None


def test_recovery_code_works_once(env):
    name = env.make()
    _, codes = env.enroll(name)
    c = env.client()
    ch = env.login(c, name).json()["challenge"]
    assert c.post("/api/v1/auth/login/mfa", json={"challenge": ch, "code": codes[0].upper()}).status_code == 200   # case-insensitive
    c2 = env.client()
    ch2 = env.login(c2, name).json()["challenge"]
    assert c2.post("/api/v1/auth/login/mfa", json={"challenge": ch2, "code": codes[0]}).status_code == 401       # used up
    assert c2.post("/api/v1/auth/login/mfa", json={"challenge": ch2, "code": codes[1].replace("-", " ")}).status_code == 200
    env.db.expire_all()
    assert len(env.db.query(User).filter(User.username == name).one().recovery_hashes) == 8
    actions = [a.action for a in env.db.query(AuditLog).filter(AuditLog.username == name)]
    assert "recovery_code_used" in actions


def test_wrong_second_factor_counts_toward_lockout(env):
    name = env.make()
    env.enroll(name)
    c = env.client()
    for _ in range(settings.LOGIN_MAX_FAILURES):
        ch = env.login(c, name).json()
        if "challenge" not in ch:
            break
        assert c.post("/api/v1/auth/login/mfa", json={"challenge": ch["challenge"], "code": "111111"}).status_code == 401
    assert env.login(c, name).status_code == 423                   # locked even though the password is right


def test_disable_needs_password_and_code(env):
    name = env.make()
    secret, codes = env.enroll(name)
    c = env.client()
    ch = env.login(c, name).json()["challenge"]
    csrf = c.post("/api/v1/auth/login/mfa", json={"challenge": ch, "code": codes[0]}).json()["csrf_token"]
    hdr = {"X-CSRF-Token": csrf}
    assert c.post("/api/v1/auth/mfa/disable", json={"password": "wrong", "code": codes[1]}, headers=hdr).status_code == 400
    assert c.post("/api/v1/auth/mfa/disable", json={"password": PASSWORD, "code": "000000"}, headers=hdr).status_code == 400
    assert c.post("/api/v1/auth/mfa/disable", json={"password": PASSWORD, "code": codes[1]}, headers=hdr).status_code == 204
    r = env.login(env.client(), name)
    assert r.json()["mfa_required"] is False and r.json()["user"]["mfa_enabled"] is False


def test_admin_can_reset_a_lost_authenticator(env):
    admin, victim = env.make("ADMIN"), env.make("VIEWER")
    env.enroll(victim)
    a = env.client()
    csrf = env.login(a, admin).json()["csrf_token"]
    listed = a.get("/api/v1/auth/users").json()
    vid = next(u["id"] for u in listed if u["username"] == victim)
    assert next(u for u in listed if u["username"] == victim)["mfa_enabled"] is True
    assert a.post(f"/api/v1/auth/users/{vid}/reset-mfa", headers={"X-CSRF-Token": csrf}).status_code == 204
    r = env.login(env.client(), victim)
    assert r.status_code == 200 and r.json()["mfa_required"] is False        # password alone works again; they re-enrol


def test_admins_are_forced_to_enrol_when_required(env, monkeypatch):
    monkeypatch.setattr(settings, "MFA_REQUIRED_FOR_ADMINS", True)
    admin, viewer = env.make("ADMIN"), env.make("VIEWER")
    a = env.client()
    body = env.login(a, admin).json()
    assert body["user"]["mfa_setup_required"] is True
    csrf = body["csrf_token"]
    r = a.get("/api/v1/promotions/top10")
    assert r.status_code == 403 and "MFA_SETUP_REQUIRED" in r.text
    assert a.get("/").headers["location"] == "/account"
    assert a.get("/account").status_code == 200
    # ... and can enrol, after which everything works
    hdr = {"X-CSRF-Token": csrf}
    secret = a.post("/api/v1/auth/mfa/setup", headers=hdr).json()["secret"]
    assert a.post("/api/v1/auth/mfa/enable", json={"code": pyotp.TOTP(secret).now()}, headers=hdr).status_code == 200
    assert a.get("/api/v1/promotions/top10").status_code == 200
    # an enrolled admin cannot turn it back off; viewers are not forced
    assert env.login(env.client(), viewer).json()["user"]["mfa_setup_required"] is False


def test_unavailable_without_secret_key(env, monkeypatch):
    monkeypatch.setattr(settings, "SECRET_KEY", "")
    name = env.make()
    c = env.client()
    csrf = env.login(c, name).json()["csrf_token"]
    r = c.post("/api/v1/auth/mfa/setup", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 503 and "SECRET_KEY" in r.json()["detail"]


def test_crypto_helpers_roundtrip_and_reject_tampering():
    settings.SECRET_KEY = "unit-test-secret-key-0123456789abcdef"
    assert crypto.decrypt(crypto.encrypt("JBSWY3DPEHPK3PXP")) == "JBSWY3DPEHPK3PXP"
    assert crypto.decrypt("not-a-token") is None
    token = crypto.sign_challenge("user-1", 60)
    assert crypto.verify_challenge(token) == "user-1"
    flipped = token[:-1] + ("0" if token[-1] != "0" else "1")      # always differs from the real signature
    assert crypto.verify_challenge(flipped) is None
    assert crypto.verify_challenge(token.replace("user-1", "user-2")) is None
    settings.SECRET_KEY = ""
