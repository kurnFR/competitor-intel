"""Which sources get crawled, when, and how failures are reported (PRD 5, 6, 18)."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.db.session import SessionLocal
from app.models.scan_run import ScanRun
from app.models.source import SourceRegistry
from app.services.crawler import manager
from app.services.crawler.manager import UnsupportedAdapter, crawlable_sources, run_all_crawlers


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        session.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"PostgreSQL is not reachable: {exc}")
    created = []

    def add(label, **kw):
        base = dict(name=f"LC {label} {uuid.uuid4().hex[:6]}", domain=f"{label}-{uuid.uuid4().hex[:6]}.example",
                    base_url=f"https://{label}-{uuid.uuid4().hex[:6]}.example/", source_type="RETAILER", adapter_key="generic_catalog",
                    approval_status="APPROVED", is_active=True, crawl_frequency_minutes=1440)
        base.update(kw)
        s = SourceRegistry(**base)
        session.add(s)
        session.flush()
        created.append(s.id)
        return s

    session.add_source = add
    # keep these tests independent of whatever other sources exist in a shared database
    others = [s.id for s in session.query(SourceRegistry).filter(SourceRegistry.is_active.is_(True)).all()]
    session.query(SourceRegistry).filter(SourceRegistry.id.in_(others)).update({"is_active": False}, synchronize_session=False)
    session.commit()
    yield session
    session.rollback()
    session.query(SourceRegistry).filter(SourceRegistry.id.in_(created)).delete(synchronize_session=False)
    session.query(SourceRegistry).filter(SourceRegistry.id.in_(others)).update({"is_active": True}, synchronize_session=False)
    session.commit()
    session.close()


def names(sources):
    return {s.name.split()[1] for s in sources}


def test_only_approved_active_sources_with_an_adapter_are_crawlable(db):
    db.add_source("ok")
    db.add_source("candidate", approval_status="CANDIDATE", is_active=False)
    db.add_source("candidate_active", approval_status="CANDIDATE", is_active=True)      # even if mis-flagged active
    db.add_source("rejected", approval_status="REJECTED", is_active=False)
    db.add_source("paused", is_active=False)
    db.add_source("noadapter", adapter_key=None)
    db.commit()
    assert names(crawlable_sources(db)) == {"ok"}


def test_each_source_follows_its_own_schedule(db):
    now = datetime.now(timezone.utc)
    db.add_source("never")
    db.add_source("due", last_crawled_at=now - timedelta(minutes=400), crawl_frequency_minutes=360)
    db.add_source("notdue", last_crawled_at=now - timedelta(minutes=100), crawl_frequency_minutes=360)
    db.add_source("daily_notdue", last_crawled_at=now - timedelta(hours=5), crawl_frequency_minutes=1440)
    db.commit()
    assert names(crawlable_sources(db, only_due=True, now=now)) == {"never", "due"}
    assert names(crawlable_sources(db, only_due=False, now=now)) == {"never", "due", "notdue", "daily_notdue"}   # Scan now = everything approved


def test_scan_now_and_scheduler_use_the_right_selection(db, monkeypatch):
    now = datetime.now(timezone.utc)
    db.add_source("fresh", last_crawled_at=now, crawl_frequency_minutes=1440)
    db.commit()
    crawled = []

    class Fake:
        client = None
        def __init__(self, src): self.src = src
        def crawl(self):
            crawled.append(self.src.name)
            return []

    monkeypatch.setitem(manager.ADAPTERS, "generic_catalog", lambda d, s: Fake(s))
    run_all_crawlers(db, only_due=True)
    assert crawled == []                                   # scheduled run: not due yet
    run_all_crawlers(db, only_due=False)
    assert len(crawled) == 1                               # manual scan: crawl all approved sources


def test_an_unsupported_adapter_is_a_visible_failure_not_a_silent_skip(db, monkeypatch):
    bad = db.add_source("badadapter", adapter_key="generic_catalog")
    db.commit()
    monkeypatch.setitem(manager.ADAPTERS, "generic_catalog", lambda d, s: (_ for _ in ()).throw(UnsupportedAdapter("nope")))
    docs = run_all_crawlers(db)
    db.expire_all()
    fresh = db.get(SourceRegistry, bad.id)
    assert docs == [] and fresh.last_error_at is not None and fresh.last_crawled_at is not None
    assert fresh.last_success_at is None            # recorded as a failure, not as "the source has no promotions"


def test_scan_history_is_recorded_for_success_and_failure(db, monkeypatch):
    import scripts.run_pipeline as rp
    monkeypatch.setattr(rp, "run_all_crawlers", lambda d, **kw: [])
    summary = rp.run_pipeline(crawl_fresh=True, max_docs=None, trigger="MANUAL", triggered_by="tester")
    assert summary["status"] == "completed"
    run = db.query(ScanRun).filter(ScanRun.triggered_by == "tester").order_by(ScanRun.started_at.desc()).first()
    assert run.status == "COMPLETED" and run.trigger == "MANUAL" and run.finished_at is not None
    assert run.summary["documents"] == 0

    def boom(d, **kw):
        raise RuntimeError("crawler exploded")
    monkeypatch.setattr(rp, "run_all_crawlers", boom)
    with pytest.raises(RuntimeError):
        rp.run_pipeline(crawl_fresh=True, max_docs=None, trigger="SCHEDULED", triggered_by="sched-test")
    failed = db.query(ScanRun).filter(ScanRun.triggered_by == "sched-test").one()
    assert failed.status == "FAILED" and "crawler exploded" in failed.error
    db.query(ScanRun).filter(ScanRun.triggered_by.in_(["tester", "sched-test"])).delete(synchronize_session=False)
    db.commit()
