"""Setup self-check: what is configured correctly, and what still needs attention.

Read-only. Never reveals secret values (only whether they are set and long enough).
"""
from __future__ import annotations

import importlib.util
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, List

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core import crypto
from app.core.config import settings
from app.models.auth import User
from app.models.resolution import ReviewQueue
from app.models.scan_run import ScanRun
from app.models.source import SourceRegistry
from app.models.promotion import Promotion
from app.services.promotions.visibility import live_promotion_filter

PASS, WARN, FAIL, INFO = "PASS", "WARN", "FAIL", "INFO"


@dataclass
class Check:
    name: str
    status: str
    detail: str
    fix: str = ""


def count_active_admins(db: Session) -> int:
    return db.query(User).filter(User.role == "ADMIN", User.is_active.is_(True)).count()


def _database(db: Session) -> Check:
    db.execute(text("SELECT 1"))
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    heads = set(ScriptDirectory.from_config(config).get_heads())
    context = MigrationContext.configure(db.connection(), opts={"version_table_schema": settings.DATABASE_SCHEMA})
    current = set(context.get_current_heads())
    if current == heads:
        return Check("Database", PASS, f"Reachable and up to date (version {', '.join(sorted(current))}).")
    return Check("Database", FAIL, f"Reachable, but the schema is at {sorted(current) or 'nothing'} and the code expects {sorted(heads)}.",
                 "Back up the database, then run: alembic upgrade head")


def _environment(db: Session) -> Check:
    if settings.APP_ENV.lower() == "production":
        return Check("Environment", PASS, "APP_ENV=production (hidden API docs, HSTS, secure cookies).")
    return Check("Environment", WARN, f"APP_ENV={settings.APP_ENV!r}: running in non-production mode.",
                 "For a real deployment set APP_ENV=production in .env.")


def _https(db: Session) -> Check:
    if settings.session_cookie_secure:
        return Check("HTTPS cookies", PASS, "Session cookies are marked Secure (they are only sent over HTTPS).")
    if settings.APP_ENV.lower() == "production":
        return Check("HTTPS cookies", FAIL, "Production mode but the session cookie is not marked Secure.",
                     "Remove SESSION_COOKIE_SECURE=false and serve the app over HTTPS (docs/DEPLOYMENT.md).")
    return Check("HTTPS cookies", INFO, "Secure cookies are off (fine for local testing over http).",
                 "In production serve over HTTPS and set APP_ENV=production.")


def _secret_key(db: Session) -> Check:
    if not settings.SECRET_KEY:
        return Check("SECRET_KEY (two-factor)", WARN, "Not set: two-factor sign-in is unavailable.",
                     'Generate once: python -c "import secrets; print(secrets.token_urlsafe(48))" and put it in .env. Never change it afterwards.')
    if not crypto.secret_key_configured() or len(settings.SECRET_KEY) < 32:
        return Check("SECRET_KEY (two-factor)", WARN, "Set but short (use at least 32 characters).",
                     "Replace it before anyone enrols in two-factor sign-in (changing it later invalidates enrolments).")
    return Check("SECRET_KEY (two-factor)", PASS, "Set and long enough; two-factor sign-in is available.")


def _admins(db: Session) -> Check:
    admins = count_active_admins(db)
    if admins == 0:
        return Check("Administrator accounts", FAIL, "There is no active administrator.",
                     "Create one: python -m scripts.create_user --username yourname --role ADMIN")
    with_2fa = db.query(User).filter(User.role == "ADMIN", User.is_active.is_(True), User.totp_enabled.is_(True)).count()
    if with_2fa < admins and settings.MFA_REQUIRED_FOR_ADMINS:
        return Check("Administrator accounts", WARN, f"{admins} admin(s); {admins - with_2fa} without two-factor but it is required.",
                     "Those admins will be sent to set it up at next sign-in.")
    note = f"{admins} active administrator(s); {with_2fa} with two-factor."
    if with_2fa < admins:
        return Check("Administrator accounts", WARN, note, "Turn on two-factor on each admin's Account page (or set MFA_REQUIRED_FOR_ADMINS=true).")
    return Check("Administrator accounts", PASS, note)


def _api_key(db: Session) -> Check:
    if not settings.ADMIN_API_KEY:
        return Check("Automation API key", INFO, "Not set (only signed-in admins can start scans). That is fine.")
    if len(settings.ADMIN_API_KEY) < 24:
        return Check("Automation API key", WARN, "ADMIN_API_KEY is set but short.",
                     'Use a long random value: python -c "import secrets; print(secrets.token_urlsafe(32))"')
    return Check("Automation API key", PASS, "Set and long enough.")


def _crawler(db: Session) -> Check:
    if not settings.CRAWLER_RESPECT_ROBOTS:
        return Check("Crawler etiquette", FAIL, "CRAWLER_RESPECT_ROBOTS is off: sites' robots.txt rules are being ignored.",
                     "Set CRAWLER_RESPECT_ROBOTS=true.")
    ua = settings.CRAWLER_USER_AGENT
    if "@" in ua or "http" in ua.lower():
        return Check("Crawler etiquette", PASS, "robots.txt is obeyed and the user agent includes contact details.")
    return Check("Crawler etiquette", WARN, "robots.txt is obeyed, but the user agent has no contact details.",
                 "Set CRAWLER_USER_AGENT=CompetitorIntelBot/1.0 (+https://your-site; you@your-company) so site owners can reach you.")


def _llm(check_connection: bool) -> Callable[[Session], Check]:
    def run(db: Session) -> Check:
        if not settings.LLM_BASE_URL or not settings.LLM_MODEL:
            return Check("LLM", FAIL, "LLM_BASE_URL / LLM_MODEL are not set; extraction cannot work.", "Set LLM_BASE_URL, LLM_API_KEY and LLM_MODEL.")
        base = f"{settings.LLM_BASE_URL.rstrip('/')} (model {settings.LLM_MODEL})"
        if not check_connection:
            return Check("LLM", INFO, f"Configured: {base}. Connection not tested.", "Tick 'test the LLM connection' (or run scripts.preflight --llm).")
        import httpx
        try:
            r = httpx.get(settings.LLM_BASE_URL.rstrip("/") + "/models", timeout=6.0,
                          headers={"Authorization": f"Bearer {settings.LLM_API_KEY}"} if settings.LLM_API_KEY else {})
        except httpx.HTTPError as exc:
            return Check("LLM", FAIL, f"Could not reach {base}: {type(exc).__name__}.", "Check LLM_BASE_URL and that the service is running and reachable from this server.")
        if r.status_code in (401, 403):
            return Check("LLM", FAIL, f"{base} refused the credentials (HTTP {r.status_code}).", "Check LLM_API_KEY.")
        if r.status_code >= 400:
            return Check("LLM", WARN, f"{base} answered HTTP {r.status_code}.", "Try: python -m scripts.try_extract sample.txt to test a real extraction.")
        return Check("LLM", PASS, f"Reachable: {base}. Run scripts.try_extract on a real page to check extraction quality.")
    return run


def _sources(db: Session) -> List[Check]:
    from app.api.v1.endpoints.sources import _health
    now = datetime.now(timezone.utc)
    sources = db.query(SourceRegistry).all()
    approved = [s for s in sources if s.approval_status == "APPROVED" and s.is_active]
    candidates = [s for s in sources if s.approval_status == "CANDIDATE"]
    out: List[Check] = []
    if not approved:
        out.append(Check("Websites to scan", WARN, "No approved, active website: nothing will be scanned.",
                         "Admin page -> Websites we scan: add one, then Approve it (or run python scripts/seed_data.py for the starter list)."))
    else:
        bad = [s.name for s in approved if _health(s, now) in ("FAILING", "STALE")]
        if bad:
            out.append(Check("Websites to scan", WARN, f"{len(approved)} approved; failing or stale: {', '.join(bad[:5])}.",
                             "Open each in a browser: the layout may have changed, it may block bots, or robots.txt disallows it."))
        else:
            out.append(Check("Websites to scan", PASS, f"{len(approved)} approved and active."))
    if candidates:
        out.append(Check("Websites awaiting approval", INFO, f"{len(candidates)} candidate(s) are not being scanned until approved.", "Admin page -> Approve or Reject."))
    sample = [s.name for s in approved if s.domain.endswith(".example") or s.name.startswith(("Test source", "Synthetic Source", "LC "))]
    if sample:
        out.append(Check("Sample/test data", WARN, f"{len(sample)} approved source(s) look like test data (e.g. {sample[0]}).",
                         "Pause or reject them on the Admin page. Never run the automated tests against your production database."))
    return out


def latest_scan(db: Session):
    return db.query(ScanRun).order_by(ScanRun.started_at.desc()).first()


def _scans(db: Session) -> Check:
    last = latest_scan(db)
    if last is None:
        return Check("Scans", WARN, "No scan has run yet.", "Admin approves a website, then use 'Scan now' on the dashboard.")
    when = last.started_at.strftime("%Y-%m-%d %H:%M UTC")
    if last.status == "FAILED":
        return Check("Scans", FAIL, f"The last scan ({when}) failed: {(last.error or '')[:120]}", "See the server log (docker compose logs app) and the Admin page's Recent scans.")
    if datetime.now(timezone.utc) - last.started_at > timedelta(days=3):
        return Check("Scans", WARN, f"The last scan was {when}, more than 3 days ago.", "Is the app running? Check the scheduler line in the log.")
    summary = last.summary or {}
    note = f"Last scan {when}: {last.status}, {summary.get('documents', '?')} page(s), {summary.get('observations', '?')} promotion(s) stored, {summary.get('rejected', '?')} rejected."
    return Check("Scans", WARN if last.status == "PARTIAL" else PASS, note,
                 "Some pages failed: check the log." if last.status == "PARTIAL" else "")


def _promotions(db: Session) -> Check:
    now = datetime.now(timezone.utc)
    live = db.query(Promotion).filter(live_promotion_filter(now, recency_days=90)).count()
    total = db.query(Promotion).count()
    if total == 0:
        return Check("Promotions", INFO, "No promotions stored yet.")
    if live == 0:
        return Check("Promotions", WARN, f"{total} stored but none pass the Top 10 checks.",
                     "Common reasons: no matched competitor/brand (see Review), source not approved, conflicts waiting, or nothing verified recently.")
    return Check("Promotions", PASS, f"{live} eligible for the dashboard (of {total} stored).")


def _review(db: Session) -> Check:
    pending = db.query(ReviewQueue).filter(ReviewQueue.status == "PENDING").count()
    conflicts = db.query(ReviewQueue).filter(ReviewQueue.status == "PENDING", ReviewQueue.entity_type == "CONFLICT").count()
    if conflicts or pending > 50:
        return Check("Review queue", WARN, f"{pending} item(s) waiting, {conflicts} of them conflict(s) that hide promotions.", "An analyst should work through the Review page.")
    return Check("Review queue", PASS if pending == 0 else INFO, f"{pending} item(s) waiting.")


def _alerts(db: Session) -> Check:
    from app.models.alert import AlertEvent
    from app.services import alerts, notify
    if not notify.any_channel_configured():
        return Check("Failure alerts", WARN, "No e-mail or chat webhook is configured, so nobody will be told when a scan or a website fails "
                     "(problems only show on this page).",
                     "Set SMTP_HOST + SMTP_FROM + DIGEST_RECIPIENTS and/or DIGEST_WEBHOOK_URL. Alerts use the same channels as the weekly digest.")
    stuck = db.query(AlertEvent).filter(AlertEvent.delivered.is_(False), AlertEvent.attempts >= alerts.MAX_ATTEMPTS).count()
    if stuck:
        return Check("Failure alerts", WARN, f"{stuck} alert(s) could not be delivered after {alerts.MAX_ATTEMPTS} attempts.",
                     "Check the SMTP / webhook settings and the server log.")
    channels = ", ".join(c for c, on in (("e-mail", notify.email_configured()), ("chat webhook", notify.webhook_configured())) if on)
    return Check("Failure alerts", PASS, f"Failures are announced once each via {channels}.")


def _storage(db: Session) -> Check:
    import os
    import shutil
    root = Path(os.getenv("RAW_DOCUMENT_STORAGE_PATH", "./data/raw_documents"))
    probe = root
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    usage = shutil.disk_usage(probe)
    used = sum(f.stat().st_size for f in root.rglob("*") if f.is_file()) if root.exists() else 0
    gb = lambda n: f"{n / 1024 ** 3:.1f} GB"
    free_pct = usage.free / usage.total * 100
    retention = (f"Pages older than {settings.RETENTION_DOCUMENT_DAYS} days are trimmed daily." if settings.RETENTION_ENABLED
                 else "Data retention is OFF, so stored pages will keep growing.")
    detail = f"Stored pages use {gb(used)}; {gb(usage.free)} free on the disk ({free_pct:.0f}%). {retention}"
    if usage.free < 2 * 1024 ** 3 or free_pct < 10:
        return Check("Disk space", FAIL if usage.free < 512 * 1024 ** 2 else WARN, detail, "Free up space or move RAW_DOCUMENT_STORAGE_PATH to a larger disk.")
    if not settings.RETENTION_ENABLED:
        return Check("Disk space", WARN, detail, "Set RETENTION_ENABLED=true (see python -m scripts.retention --dry-run).")
    return Check("Disk space", PASS, detail)


def _optional(db: Session) -> Check:
    from app.services.digest import digest_configured
    bits = [f"weekly digest: {'on' if digest_configured() else 'off'}",
            f"JavaScript-only sites (Playwright): {'installed' if importlib.util.find_spec('playwright') else 'not installed'}"]
    return Check("Optional features", INFO, "; ".join(bits))


def run_checks(db: Session, *, check_llm: bool = False) -> List[Check]:
    """Run every check; one failing check never hides the others."""
    steps: List[Callable[[Session], object]] = [
        _database, _environment, _https, _secret_key, _admins, _api_key, _crawler, _llm(check_llm), _sources, _scans, _alerts, _storage, _promotions, _review, _optional]
    results: List[Check] = []
    for step in steps:
        try:
            out = step(db)
            results.extend(out if isinstance(out, list) else [out])
        except Exception as exc:                      # a broken check is itself a finding
            db.rollback()
            results.append(Check(getattr(step, "__name__", "check").lstrip("_").replace("_", " ").title(), FAIL,
                                 f"The check itself failed: {type(exc).__name__}: {str(exc)[:120]}"))
    return results


def summarize(checks: List[Check]) -> dict:
    counts = {PASS: 0, WARN: 0, FAIL: 0, INFO: 0}
    for c in checks:
        counts[c.status] += 1
    return {**counts, "ready": counts[FAIL] == 0}


def as_dict(checks: List[Check]) -> dict:
    return {"summary": summarize(checks), "checks": [asdict(c) for c in checks]}
