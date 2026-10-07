"""Failure alerts: announced once per problem, retried when delivery fails, recovery noted."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.db.session import SessionLocal
from app.models.alert import AlertEvent
from app.models.scan_run import ScanRun
from app.models.source import SourceRegistry
from app.services import alerts

NOW = datetime.now(timezone.utc)


@pytest.fixture()
def env(monkeypatch):
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"PostgreSQL is not reachable: {exc}")
    # Keep the test independent of other sources/scans in a shared database.
    others = [s.id for s in db.query(SourceRegistry).filter(SourceRegistry.is_active.is_(True)).all()]
    db.query(SourceRegistry).filter(SourceRegistry.id.in_(others)).update({"is_active": False}, synchronize_session=False)
    marker = ScanRun(started_at=NOW + timedelta(hours=1), trigger="CLI", triggered_by="alerts-test-marker", status="COMPLETED")
    db.add(marker)
    db.commit()
    created, runs = [], [marker.id]

    def source(label, **kw):
        base = dict(name=f"AL {label} {uuid.uuid4().hex[:5]}", domain=f"al-{uuid.uuid4().hex[:6]}.example", base_url=f"https://al-{uuid.uuid4().hex[:6]}.example/",
                    source_type="RETAILER", adapter_key="generic_catalog", approval_status="APPROVED", is_active=True,
                    last_crawled_at=NOW, last_success_at=NOW)
        base.update(kw)
        s = SourceRegistry(**base)
        db.add(s)
        db.commit()
        created.append(s.id)
        return s

    def scan(status, error=None, hours=2):
        r = ScanRun(started_at=NOW + timedelta(hours=hours), trigger="CLI", triggered_by="alerts-test", status=status, error=error)
        db.add(r)
        db.commit()
        runs.append(r.id)
        return r

    sent = []
    state = {"channels": True, "result": {"email": True}}
    monkeypatch.setattr(alerts.notify, "any_channel_configured", lambda: state["channels"])
    monkeypatch.setattr(alerts.notify, "send_text", lambda subject, body: (sent.append((subject, body)) or dict(state["result"])))

    def mine(kind=None):
        ids = {str(i) for i in created} | {str(i) for i in runs}
        q = [e for e in db.query(AlertEvent).all() if e.subject_id in ids]
        return [e for e in q if kind is None or e.kind == kind]

    yield type("Env", (), dict(db=db, source=staticmethod(source), scan=staticmethod(scan), sent=sent, state=state, mine=staticmethod(mine)))
    db.rollback()
    ids = {str(i) for i in created} | {str(i) for i in runs}
    for e in db.query(AlertEvent).all():
        if e.subject_id in ids:
            db.delete(e)
    db.query(ScanRun).filter(ScanRun.id.in_(runs)).delete(synchronize_session=False)
    db.query(SourceRegistry).filter(SourceRegistry.id.in_(created)).delete(synchronize_session=False)
    db.query(SourceRegistry).filter(SourceRegistry.id.in_(others)).update({"is_active": True}, synchronize_session=False)
    db.commit()
    db.close()


def test_a_failing_source_is_announced_once_however_many_scans_see_it(env):
    s = env.source("broken", last_error_at=NOW, last_success_at=NOW - timedelta(days=1))
    for _ in range(4):                                   # four scans, same ongoing problem
        alerts.check_and_alert(env.db)
    (event,) = env.mine("SOURCE_FAILING")
    assert s.name in event.title and "Last successful check" in event.body and "never read as 'no promotions'" in event.body
    assert len([m for m in env.sent if s.name in m[0]]) == 1
    assert event.delivered and event.delivery == "email"


def test_recovery_is_announced_and_a_new_failure_is_a_new_announcement(env):
    s = env.source("flaky", last_error_at=NOW, last_success_at=NOW - timedelta(days=1))
    alerts.check_and_alert(env.db)
    s.last_success_at, s.last_crawled_at = NOW + timedelta(minutes=5), NOW + timedelta(minutes=5)     # it works again
    env.db.commit()
    alerts.check_and_alert(env.db)
    alerts.check_and_alert(env.db)
    (recovered,) = env.mine("SOURCE_RECOVERED")
    assert "scanned successfully again" in recovered.body
    assert env.mine("SOURCE_FAILING")[0].resolved_at is not None
    s.last_error_at = NOW + timedelta(hours=3)                                                       # it breaks again later
    env.db.commit()
    alerts.check_and_alert(env.db)
    assert len(env.mine("SOURCE_FAILING")) == 2


def test_no_recovery_note_for_a_source_that_was_never_reported(env):
    env.source("fine")
    alerts.check_and_alert(env.db)
    assert env.mine() == [] and env.sent == []


def test_stale_source_is_announced(env):
    s = env.source("stale", last_success_at=NOW - timedelta(days=5), last_crawled_at=NOW - timedelta(days=5))
    alerts.check_and_alert(env.db)
    (event,) = env.mine("SOURCE_STALE")
    assert s.name in event.title and "3+ days" in event.title


def test_only_approved_active_sources_are_watched(env):
    env.source("cand", approval_status="CANDIDATE", is_active=False, last_error_at=NOW, last_success_at=None)
    env.source("rej", approval_status="REJECTED", is_active=False, last_error_at=NOW, last_success_at=None)
    env.source("paused", is_active=False, last_error_at=NOW, last_success_at=None)
    env.source("never", last_crawled_at=None, last_success_at=None)
    alerts.check_and_alert(env.db)
    assert env.mine() == []


def test_failed_scan_is_announced_once_and_completed_scans_are_not(env):
    run = env.scan("FAILED", error="RuntimeError: crawler exploded")
    alerts.check_and_alert(env.db)
    alerts.check_and_alert(env.db)
    (event,) = env.mine("SCAN_FAILED")
    assert "crawler exploded" in event.body and event.subject_id == str(run.id)
    env.scan("COMPLETED", hours=3)                       # a newer, healthy scan: nothing new to say
    alerts.check_and_alert(env.db)
    assert len(env.mine("SCAN_FAILED")) == 1


def test_failed_delivery_is_retried_then_given_up(env):
    env.source("retry", last_error_at=NOW, last_success_at=NOW - timedelta(days=1))
    env.state["result"] = {"email": False}
    for _ in range(alerts.MAX_ATTEMPTS + 3):
        stats = alerts.check_and_alert(env.db)
    (event,) = env.mine("SOURCE_FAILING")
    assert not event.delivered and event.attempts == alerts.MAX_ATTEMPTS and "email" in event.last_error
    assert stats["sent"] == 0

    env.state["result"] = {"email": True}                # a later success on a fresh problem still works
    env.source("other", last_error_at=NOW, last_success_at=NOW - timedelta(days=2))
    alerts.check_and_alert(env.db)
    assert [e for e in env.mine("SOURCE_FAILING") if e.delivered and "other" in e.title.lower()]


def test_delivery_succeeding_on_retry_marks_it_delivered(env):
    env.source("late", last_error_at=NOW, last_success_at=NOW - timedelta(days=1))
    env.state["result"] = {"email": False}
    alerts.check_and_alert(env.db)
    env.state["result"] = {"email": True}
    stats = alerts.check_and_alert(env.db)
    (event,) = env.mine("SOURCE_FAILING")
    assert event.delivered and event.attempts == 2 and event.last_error is None and stats["sent"] == 1


def test_partial_delivery_is_not_resent_to_the_channel_that_worked(env):
    env.source("partial", last_error_at=NOW, last_success_at=NOW - timedelta(days=1))
    env.state["result"] = {"email": True, "webhook": False}
    alerts.check_and_alert(env.db)
    alerts.check_and_alert(env.db)
    (event,) = env.mine("SOURCE_FAILING")
    assert event.delivered and event.delivery == "partial: email" and "webhook" in event.last_error
    assert len(env.sent) == 1


def test_without_any_channel_the_alert_is_kept_visible_not_retried(env):
    env.state["channels"] = False
    env.source("quiet", last_error_at=NOW, last_success_at=NOW - timedelta(days=1))
    alerts.check_and_alert(env.db)
    alerts.check_and_alert(env.db)
    (event,) = env.mine("SOURCE_FAILING")
    assert event.delivery.startswith("not sent: no e-mail or webhook") and env.sent == [] and event.attempts == 0
