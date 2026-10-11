"""The whole path, for real: HTTP fetch (+robots.txt) -> page text -> LLM call -> validation -> matching -> storage -> dashboard.

A small fake retailer website and a fake OpenAI-compatible LLM server run on local ports. Nothing in the application is
mocked: the real crawler fetches the page, the real OpenAI client calls the fake LLM, the real pipeline stores the result.
"""
import json
import re
import threading
import uuid
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.config import settings
from app.db.session import SessionLocal
from app.main import app
from app.models.alert import AlertEvent
from app.models.auth import AuditLog, User
from app.models.entity import Brand, Competitor
from app.models.promotion import Promotion, PromotionEvidence, PromotionObservation
from app.models.promotion_change import PromotionChangeEvent
from app.models.resolution import ReviewQueue
from app.models.scan_run import ScanRun
from app.models.source import CrawlDocument, CrawlJob, SourceRegistry
from app.services import alerts, auth as auth_service
from app.services.crawler import base as crawler_base
from app.services.entity_resolution.resolver import normalize_str
from app.services.storage import LocalRawDocumentStore

PASSWORD = "Correct-Horse-Battery-9"


# ----------------------------------------------------------------------------- fake website and fake LLM
def _server(handler_cls, state):
    class Server(ThreadingHTTPServer):
        daemon_threads = True
    srv = Server(("127.0.0.1", 0), handler_cls)
    srv.state = state
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


class SiteHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        st = self.server.state
        st["hits"].append((self.path, self.headers.get("User-Agent", "")))
        body, ctype, code = None, "text/html; charset=utf-8", 200
        if self.path == "/robots.txt":
            body, ctype = st["robots"], "text/plain"
        elif self.path in st["pages"]:
            body = st["pages"][self.path]
        else:
            body, code = "not found", 404
        data = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class LLMHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        st = self.server.state
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        prompt = payload["messages"][-1]["content"]
        st["calls"].append(prompt)
        if st["mode"] == "error":
            data = json.dumps({"error": {"message": "model unavailable", "type": "invalid_request_error"}}).encode()
            self.send_response(400)
        else:
            content = json.dumps({"promotions": st["respond"](prompt)})
            data = json.dumps({"id": "x", "object": "chat.completion", "created": 0, "model": payload.get("model", "fake"),
                               "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
                               "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}).encode()
            self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def dots(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def promo_page(tag: str, price: int, end_iso: str) -> str:
    return (f"<html><head><title>Promo Biskuit</title></head><body>"
            f'<div class="catalog-item">Biskuit Zz{tag}Roma Kelapa 300g Diskon 30% jadi Rp {dots(price)} (normal Rp 10.000) '
            f"berlaku di wilayah Jawa sampai {end_iso}. Promo hemat di Indomaret!</div>"
            f'<div class="catalog-item">Malkist Zz{tag}Abon 250g Beli 2 gratis 1 harga Rp 9.000 per pack promo hemat</div></body></html>')


def make_responder(tag: str):
    """Stands in for the model: reads the page text in the prompt and answers with quotes copied from it."""
    def respond(prompt: str):
        items = []
        m = re.search(rf"Biskuit (Zz{tag}Roma Kelapa 300g) Diskon (\d+)% jadi Rp ([\d.]+) \(normal Rp ([\d.]+)\) berlaku di wilayah (\w+) sampai (\d{{4}}-\d{{2}}-\d{{2}})", prompt)
        if m:
            items.append({"product_name": m.group(1), "brand": f"Zz{tag}Roma", "category": "BISCUIT", "pack_size": "300g",
                          "regular_price": int(m.group(4).replace(".", "")), "promo_price": int(m.group(3).replace(".", "")),
                          "discount_percentage": int(m.group(2)), "promotion_type": "DISCOUNT", "end_date": m.group(6),
                          "retailer": "Indomaret", "geography": m.group(5), "evidence_quote": m.group(0), "confidence": 0.92})
        m = re.search(rf"Malkist (Zz{tag}Abon 250g) Beli 2 gratis 1 harga Rp ([\d.]+) per pack", prompt)
        if m:
            items.append({"product_name": m.group(1), "brand": f"Zz{tag}Unknownbrand", "category": "CRACKER", "pack_size": "250g",
                          "promo_price": int(m.group(2).replace(".", "")), "promotion_type": "BUY_X_GET_Y", "buy_quantity": 2, "free_quantity": 1,
                          "retailer": "Indomaret", "evidence_quote": m.group(0), "confidence": 0.9})
        return items
    return respond


# ----------------------------------------------------------------------------- fixture
@pytest.fixture()
def world(monkeypatch, tmp_path):
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"PostgreSQL is not reachable: {exc}")
    import app.main as main
    # "Scan now" crawls EVERY approved source. Pause all others so this test only ever talks to its own fake website
    # (never the real retailer sites seeded in the database) and does not wait on unreachable ones.
    others = [r[0] for r in db.query(SourceRegistry.id).filter(SourceRegistry.is_active.is_(True)).all()]
    db.query(SourceRegistry).filter(SourceRegistry.id.in_(others)).update({"is_active": False}, synchronize_session=False)
    db.commit()
    auth_service.ip_throttle.clear()
    crawler_base._robots_cache.clear()
    main.pipeline_state.update(status="idle")
    tag = uuid.uuid4().hex[:6]
    end_iso = (date.today() + timedelta(days=45)).isoformat()

    site = _server(SiteHandler, {"hits": [], "robots": "User-agent: *\nAllow: /\n", "pages": {"/promo": promo_page(tag, 7000, end_iso)}})
    llm = _server(LLMHandler, {"calls": [], "mode": "ok", "respond": make_responder(tag)})
    monkeypatch.setattr(settings, "LLM_BASE_URL", f"http://127.0.0.1:{llm.server_port}/v1")
    monkeypatch.setattr(settings, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(settings, "CRAWLER_ALLOW_PRIVATE_NETWORKS", True)       # the only way to reach a local test site
    monkeypatch.setattr(settings, "CRAWLER_RESPECT_ROBOTS", True)
    monkeypatch.setattr(settings, "CRAWLER_USER_AGENT", "CompetitorIntelBot/1.0 (+test)")
    store = LocalRawDocumentStore(str(tmp_path / "raw"))
    monkeypatch.setattr(crawler_base, "get_raw_document_store", lambda: store)
    alerts_channels = {"on": False}
    monkeypatch.setattr(alerts.notify, "any_channel_configured", lambda: alerts_channels["on"])

    competitor = Competitor(name=f"Zz{tag} Rival", normalized_name=normalize_str(f"Zz{tag} Rival"), is_active=True)
    db.add(competitor)
    db.flush()
    db.add(Brand(name=f"Zz{tag}Roma", normalized_name=normalize_str(f"Zz{tag}Roma"), competitor_id=competitor.id))
    username = f"e2e_{tag}"
    auth_service.create_user(db, username=username, password=PASSWORD, role="ADMIN")
    db.commit()

    client = TestClient(app, follow_redirects=False)
    csrf = client.post("/api/v1/auth/login", json={"username": username, "password": PASSWORD}).json()["csrf_token"]
    hdr = {"X-CSRF-Token": csrf}
    url = f"http://127.0.0.1:{site.server_port}/promo"
    created = client.post("/api/v1/sources/", json={"name": f"Zz{tag} Retailer", "base_url": url, "source_type": "RETAILER",
                                                    "adapter_key": "generic_catalog"}, headers=hdr)
    assert created.status_code == 201, created.text
    source_id = created.json()["id"]
    assert client.post(f"/api/v1/sources/{source_id}/approve", json={}, headers=hdr).status_code == 200

    def scan():
        main.pipeline_state.update(status="idle")
        r = client.post("/api/v1/pipeline/run", headers=hdr)
        assert r.status_code == 202, r.text
        history = client.get("/api/v1/pipeline/status").json()["history"]
        return next(h for h in history if h["triggered_by"] == username)

    def top10():
        items = client.get(f"/api/v1/promotions/top10?q=Zz{tag}").json()["promotions"]
        return {i["product_name"][len(f"Zz{tag}"):]: i for i in items}

    def promo(name):
        db.expire_all()
        return db.query(Promotion).filter(Promotion.product_name == f"Zz{tag}{name}").first()

    def source_row():
        db.expire_all()
        return db.get(SourceRegistry, source_id)

    yield type("World", (), dict(db=db, tag=tag, site=site, llm=llm, client=client, hdr=hdr, scan=staticmethod(scan), top10=staticmethod(top10),
                                 promo=staticmethod(promo), source_row=staticmethod(source_row), source_id=source_id, end_iso=end_iso, url=url,
                                 username=username, alerts_channels=alerts_channels, competitor=competitor))
    # ---- cleanup: remove everything this test created
    site.shutdown()
    llm.shutdown()
    db.rollback()
    pids = [p.id for p in db.query(Promotion).filter(Promotion.source_id == source_id).all()]
    if pids:
        for model in (ReviewQueue, PromotionChangeEvent, PromotionEvidence, PromotionObservation):
            db.query(model).filter(model.promotion_id.in_(pids)).delete(synchronize_session=False)
        db.query(Promotion).filter(Promotion.id.in_(pids)).delete(synchronize_session=False)
    db.query(AlertEvent).filter(AlertEvent.subject_id == source_id).delete(synchronize_session=False)
    db.query(CrawlJob).filter(CrawlJob.source_id == source_id).delete(synchronize_session=False)
    db.query(CrawlDocument).filter(CrawlDocument.source_id == source_id).delete(synchronize_session=False)
    db.query(SourceRegistry).filter(SourceRegistry.id == source_id).delete(synchronize_session=False)
    db.query(SourceRegistry).filter(SourceRegistry.id.in_(others)).update({"is_active": True}, synchronize_session=False)
    db.query(Brand).filter(Brand.competitor_id == competitor.id).delete(synchronize_session=False)
    db.query(Competitor).filter(Competitor.id == competitor.id).delete(synchronize_session=False)
    db.query(ScanRun).filter(ScanRun.triggered_by == username).delete(synchronize_session=False)
    db.query(AuditLog).filter(AuditLog.username == username).delete(synchronize_session=False)
    db.query(User).filter(User.username == username).delete(synchronize_session=False)
    db.commit()
    db.close()
    auth_service.ip_throttle.clear()
    crawler_base._robots_cache.clear()


# ----------------------------------------------------------------------------- the journeys
def test_first_scan_unchanged_rescan_and_a_price_change(world):
    w = world
    # 1. first scan: a real fetch, a real LLM call, a real store
    run = w.scan()
    assert run["status"] == "COMPLETED" and run["trigger"] == "MANUAL"
    assert run["summary"]["documents"] == 1 and run["summary"]["observations"] == 2 and run["summary"]["rejected"] == 0
    paths = [p for p, _ in w.site.state["hits"]]
    assert "/robots.txt" in paths and "/promo" in paths                                      # robots.txt is read before the page
    assert all("CompetitorIntelBot" in ua for _, ua in w.site.state["hits"])                 # and the crawler says who it is
    assert len(w.llm.state["calls"]) == 1 and f"Zz{w.tag}Roma Kelapa 300g" in w.llm.state["calls"][0]

    shown = w.top10()
    assert set(shown) == {"Roma Kelapa 300g"}                                                # the unmatched brand is held back, honestly
    roma = shown["Roma Kelapa 300g"]
    assert (roma["promo_price"], roma["effective_discount"], roma["geography"], roma["geography_region"]) == (7000, 30, "Jawa", "JAWA")
    assert roma["valid_until"] == w.end_iso and roma["dates_stated"] is True and roma["source_url"] == w.url
    assert "Diskon 30%" in roma["evidence_quote"] and roma["source_status"] == "Verified source"
    assert roma["competitor"] == f"Zz{w.tag} Rival" and len(roma["score_breakdown"]["components"]) == 7

    abon = w.promo("Abon 250g")
    from app.services.promotions.visibility import why_hidden
    assert [r["key"] for r in why_hidden(w.db, abon.id)] == ["identity"]                     # explained, not mysterious
    review = [i for i in w.client.get("/api/v1/review/?limit=200").json() if i["promotion_id"] == str(abon.id)]
    assert any(i["entity_type"] == "BRAND" for i in review)                                  # and queued for a person
    assert abon.promotion_type == "BUY_X_GET_Y" and abon.geography is None and abon.geography_region == "UNKNOWN"   # nothing invented

    src = w.source_row()
    assert src.last_success_at and src.last_processed_at and src.last_error_at is None
    health = {s["id"]: s for s in w.client.get("/api/v1/sources/").json()}[w.source_id]["health"]
    assert health == "OK"
    first_verified = w.promo("Roma Kelapa 300g").last_verified_at

    # 2. same page again: no new model call, but the promotion is re-confirmed
    run = w.scan()
    assert run["summary"]["documents_skipped_unchanged"] == 1 and len(w.llm.state["calls"]) == 1
    assert w.promo("Roma Kelapa 300g").last_verified_at > first_verified

    # 3. the retailer drops the price: a new page, a new model call, and the change is recorded
    w.site.state["pages"]["/promo"] = promo_page(w.tag, 6500, w.end_iso)
    run = w.scan()
    assert run["status"] == "COMPLETED" and len(w.llm.state["calls"]) == 2
    assert w.top10()["Roma Kelapa 300g"]["promo_price"] == 6500
    changes = w.client.get(f"/api/v1/promotions/{w.promo('Roma Kelapa 300g').id}/changes").json()
    assert any(c["field_name"] == "promo_price" and c["new_value"] in (6500, "6500", 6500.0) for c in changes)
    assert w.db.query(CrawlDocument).filter(CrawlDocument.source_id == w.source_id).count() == 2      # both versions kept as evidence


def test_robots_txt_blocks_the_scan_and_a_blocked_site_is_never_read_as_having_no_promotions(world):
    w = world
    w.scan()
    assert set(w.top10()) == {"Roma Kelapa 300g"}

    w.site.state["robots"] = "User-agent: *\nDisallow: /\n"
    crawler_base._robots_cache.clear()
    hits_before = len(w.site.state["hits"])
    w.site.state["pages"]["/promo"] = "<html><body>THIS MUST NOT BE FETCHED</body></html>"
    run = w.scan()
    assert [p for p, _ in w.site.state["hits"][hits_before:]] == ["/robots.txt"]               # asked, was told no, did not fetch the page
    assert len(w.llm.state["calls"]) == 1                                                        # nothing new reached the model
    src = w.source_row()
    assert src.last_error_at and src.last_error_at >= src.last_success_at
    assert {s["id"]: s for s in w.client.get("/api/v1/sources/").json()}[w.source_id]["health"] == "FAILING"
    assert set(w.top10()) == {"Roma Kelapa 300g"} and w.promo("Roma Kelapa 300g").status == "ACTIVE"   # failure != "zero promotions"
    assert run["summary"]["documents"] == 0

    alerts.check_and_alert(w.db)                                                                  # and a person is told, once
    events = w.db.query(AlertEvent).filter(AlertEvent.subject_id == w.source_id, AlertEvent.kind == "SOURCE_FAILING").all()
    assert len(events) == 1 and f"Zz{w.tag} Retailer" in events[0].title
    alerts.check_and_alert(w.db)
    assert w.db.query(AlertEvent).filter(AlertEvent.subject_id == w.source_id, AlertEvent.kind == "SOURCE_FAILING").count() == 1


def test_an_llm_outage_keeps_old_data_and_the_page_is_retried_after_recovery(world):
    w = world
    w.scan()
    processed_at = w.source_row().last_processed_at
    w.site.state["pages"]["/promo"] = promo_page(w.tag, 6000, w.end_iso)

    w.llm.state["mode"] = "error"                                                                 # the model is down
    run = w.scan()
    assert run["status"] == "PARTIAL" and run["summary"]["documents_failed"] == 1
    assert w.top10()["Roma Kelapa 300g"]["promo_price"] == 7000                                   # the old, verified value stays
    assert w.source_row().last_processed_at == processed_at                                      # a failed extraction is not a successful check

    w.llm.state["mode"] = "ok"                                                                    # recovered: the SAME page is processed now
    run = w.scan()
    assert run["status"] == "COMPLETED" and run["summary"]["documents_skipped_unchanged"] == 0
    assert w.top10()["Roma Kelapa 300g"]["promo_price"] == 6000
    assert w.source_row().last_processed_at > processed_at
