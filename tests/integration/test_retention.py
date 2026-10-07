"""Retention trims old crawled pages but never the newest of a website, and never anything outside the store."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.db.session import SessionLocal
from app.models.alert import AlertEvent
from app.models.auth import AuditLog
from app.models.scan_run import ScanRun
from app.models.source import CrawlDocument, SourceRegistry
from app.services.retention import MIN_DOCUMENT_DAYS, run_retention
from app.services.storage import LocalRawDocumentStore

NOW = datetime.now(timezone.utc)


@pytest.fixture()
def env(tmp_path):
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"PostgreSQL is not reachable: {exc}")
    store = LocalRawDocumentStore(str(tmp_path / "raw"))
    tag = uuid.uuid4().hex[:8]
    src = SourceRegistry(name=f"RT {tag}", domain=f"rt-{tag}.example", base_url=f"https://rt-{tag}.example/", source_type="RETAILER",
                         adapter_key="generic_catalog", approval_status="CANDIDATE", is_active=False)
    db.add(src)
    db.commit()

    def doc(age_days, *, url="https://x.test/promo", body=b"<html>promo</html>", text_body="promo text", processed=True):
        stored = store.put(body + str(uuid.uuid4()).encode(), "text/html", str(src.id), "html")
        d = CrawlDocument(source_id=src.id, url=url, text_content=text_body, content_hash=uuid.uuid4().hex * 2, http_status=200,
                          retrieved_at=NOW - timedelta(days=age_days), raw_content_uri=stored.uri, raw_content_sha256=stored.sha256,
                          raw_content_size_bytes=stored.size_bytes, metadata_json={"pipeline_processed_at": "x"} if processed else {})
        db.add(d)
        db.commit()
        return d

    yield type("Env", (), dict(db=db, store=store, src=src, doc=staticmethod(doc), tag=tag))
    db.rollback()
    db.query(CrawlDocument).filter(CrawlDocument.source_id == src.id).delete(synchronize_session=False)
    db.query(SourceRegistry).filter(SourceRegistry.id == src.id).delete(synchronize_session=False)
    db.commit()
    db.close()


def reload(env, d):
    env.db.expire_all()
    return env.db.get(CrawlDocument, d.id)


def only_mine(env):
    """run_retention works on the whole database; these assertions look at this test's pages."""
    return run_retention(env.db, store=env.store)


def test_old_pages_lose_files_and_text_but_keep_their_record(env):
    old1, old2, newest = env.doc(200), env.doc(120), env.doc(1)
    freed = only_mine(env)
    assert freed["documents_trimmed"] >= 2
    for d in (old1, old2):
        d = reload(env, d)
        assert d.text_content is None and d.raw_content_uri is None and d.content_hash and d.url and d.raw_content_sha256
        assert "retention_purged_at" in d.metadata_json and d.metadata_json["pipeline_processed_at"] == "x"     # history intact
    keep = reload(env, newest)
    assert keep.text_content == "promo text" and keep.raw_content_uri is not None
    assert env.store.get(keep.raw_content_uri)                                                                 # the file is still there


def test_the_newest_page_of_a_website_is_never_removed_however_old(env):
    only_page = env.doc(400, url="https://x.test/only-one")
    other_site_old = env.doc(500, url="https://x.test/changing")
    other_site_new = env.doc(450, url="https://x.test/changing")                                                # newer than the other, still ancient
    only_mine(env)
    assert reload(env, only_page).text_content == "promo text"
    assert reload(env, other_site_new).text_content == "promo text"                                            # newest of its page: kept
    assert reload(env, other_site_old).text_content is None                                                    # superseded: trimmed


def test_recent_pages_are_untouched_and_the_minimum_age_is_enforced(env, monkeypatch):
    from app.core.config import settings
    young = env.doc(20)
    newer = env.doc(1)
    monkeypatch.setattr(settings, "RETENTION_DOCUMENT_DAYS", 1)                  # an unsafe setting is raised to the minimum
    only_mine(env)
    assert MIN_DOCUMENT_DAYS == 14
    assert reload(env, newer).text_content == "promo text"
    assert reload(env, young).text_content is None                              # 20 days old > the 14-day floor, and superseded
    very_young = env.doc(5, url="https://x.test/other")
    env.doc(2, url="https://x.test/other")
    only_mine(env)
    assert reload(env, very_young).text_content == "promo text"                 # younger than the floor, even though superseded


def test_a_file_shared_with_a_kept_page_is_not_deleted(env):
    old = env.doc(200)
    keep = env.doc(1)
    keep.raw_content_uri = old.raw_content_uri                                  # two records pointing at one stored file
    env.db.commit()
    only_mine(env)
    assert reload(env, old).text_content is None
    assert reload(env, old).raw_content_uri == old.raw_content_uri              # file kept: a retained record still needs it
    assert env.store.get(keep.raw_content_uri)


def test_dry_run_reports_but_changes_nothing(env):
    old, _ = env.doc(200), env.doc(1)
    report = run_retention(env.db, dry_run=True, store=env.store)
    assert report["dry_run"] is True and report["documents_trimmed"] >= 1 and report["bytes_freed"] > 0
    d = reload(env, old)
    assert d.text_content == "promo text" and d.raw_content_uri and env.store.get(d.raw_content_uri)


def test_store_refuses_to_delete_outside_itself(env, tmp_path):
    outside = tmp_path / "precious.txt"
    outside.write_text("do not delete")
    with pytest.raises(ValueError):
        env.store.delete(f"file://{outside}")
    assert outside.exists()
    assert env.store.delete(f"file://{env.store.root}/missing/file.bin") == 0
    with pytest.raises(ValueError):
        env.store.delete("s3://bucket/key")


def test_old_audit_scan_and_alert_rows_are_pruned_recent_ones_kept(env):
    marker = f"ret-{env.tag}"
    env.db.add_all([
        AuditLog(username=marker, action="old", occurred_at=NOW - timedelta(days=400)),
        AuditLog(username=marker, action="recent", occurred_at=NOW - timedelta(days=10)),
        ScanRun(triggered_by=marker, trigger="CLI", status="COMPLETED", started_at=NOW - timedelta(days=300)),
        ScanRun(triggered_by=marker, trigger="CLI", status="COMPLETED", started_at=NOW - timedelta(days=5)),
        AlertEvent(fingerprint=f"{marker}-old", kind="X", title="t", body="b", created_at=NOW - timedelta(days=300)),
        AlertEvent(fingerprint=f"{marker}-new", kind="X", title="t", body="b", created_at=NOW - timedelta(days=3)),
    ])
    env.db.commit()
    try:
        only_mine(env)
        assert [a.action for a in env.db.query(AuditLog).filter(AuditLog.username == marker)] == ["recent"]
        assert env.db.query(ScanRun).filter(ScanRun.triggered_by == marker).count() == 1
        assert [a.fingerprint for a in env.db.query(AlertEvent).filter(AlertEvent.fingerprint.like(f"{marker}%"))] == [f"{marker}-new"]
    finally:
        env.db.query(AuditLog).filter(AuditLog.username == marker).delete(synchronize_session=False)
        env.db.query(ScanRun).filter(ScanRun.triggered_by == marker).delete(synchronize_session=False)
        env.db.query(AlertEvent).filter(AlertEvent.fingerprint.like(f"{marker}%")).delete(synchronize_session=False)
        env.db.commit()
