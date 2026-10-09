"""Tell a person when unattended operation breaks, once per problem (not once per scan).

Problems detected:
* a scan failed outright
* an approved website is FAILING (its latest attempt failed and it has not worked since)
* an approved website is STALE (no successful check for more than 3 days)
and, when a website that was reported works again, a short "recovered" note.

Each problem has a fingerprint, so it is announced once however many scans see it. Messages go to the same e-mail
recipients / chat webhook as the weekly digest. Delivery failures are retried on later runs.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.alert import AlertEvent
from app.models.scan_run import ScanRun
from app.models.source import SourceRegistry
from app.services import notify
from app.services.source_health import compute_health

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
SOURCE_KINDS = ("SOURCE_FAILING", "SOURCE_STALE")


def _stamp(value: Optional[datetime]) -> str:
    return value.strftime("%Y-%m-%d %H:%M UTC") if value else "never"


def _raise(db: Session, *, kind: str, fingerprint: str, title: str, body: str, subject_id: Optional[str] = None) -> Optional[AlertEvent]:
    """Create the alert unless this exact problem was already announced."""
    if db.query(AlertEvent.id).filter(AlertEvent.fingerprint == fingerprint).first() is not None:
        return None
    event = AlertEvent(fingerprint=fingerprint, kind=kind, subject_id=subject_id, title=title[:200], body=body)
    db.add(event)
    db.flush()
    return event


def detect(db: Session, *, now: Optional[datetime] = None) -> List[AlertEvent]:
    """Create events for every new problem (and recovery). Does not send anything."""
    now = now or datetime.now(timezone.utc)
    created: List[AlertEvent] = []

    last = db.query(ScanRun).order_by(ScanRun.started_at.desc()).first()
    if last is not None and last.status == "FAILED":
        e = _raise(db, kind="SCAN_FAILED", fingerprint=f"scan-failed:{last.id}", subject_id=str(last.id),
                   title="Scan failed",
                   body=f"The scan started {_stamp(last.started_at)} failed: {(last.error or 'no details recorded')[:300]}\n"
                        "See Admin -> Recent scans and the server log.")
        created.append(e) if e else None

    sources = db.query(SourceRegistry).filter(SourceRegistry.approval_status == "APPROVED").all()
    for s in sources:
        health = compute_health(s, now)
        episode = _stamp(s.last_success_at)
        if health == "FAILING":
            e = _raise(db, kind="SOURCE_FAILING", fingerprint=f"source-failing:{s.id}:{episode}", subject_id=str(s.id),
                       title=f"Website failing: {s.name}",
                       body=f"{s.name} ({s.domain}) could not be scanned. Last successful check: {episode}.\n"
                            "Its promotions stay as they were (a failed scan is never read as 'no promotions'), but they are going out of date.\n"
                            "Check the site in a browser: the layout may have changed, it may block bots, or its robots.txt may disallow it.")
            created.append(e) if e else None
        elif health == "STALE":
            e = _raise(db, kind="SOURCE_STALE", fingerprint=f"source-stale:{s.id}:{episode}", subject_id=str(s.id),
                       title=f"No successful check for 3+ days: {s.name}",
                       body=f"{s.name} ({s.domain}) was last checked successfully {episode}. Is the app running and is the schedule right?")
            created.append(e) if e else None
        elif health == "OK":
            open_problems = db.query(AlertEvent).filter(AlertEvent.subject_id == str(s.id), AlertEvent.kind.in_(SOURCE_KINDS),
                                                        AlertEvent.resolved_at.is_(None)).all()
            if open_problems:
                for problem in open_problems:
                    problem.resolved_at = now
                e = _raise(db, kind="SOURCE_RECOVERED", fingerprint=f"source-recovered:{s.id}:{episode}", subject_id=str(s.id),
                           title=f"Website recovered: {s.name}", body=f"{s.name} is being scanned successfully again (last check {episode}).")
                created.append(e) if e else None
    return created


def deliver_pending(db: Session) -> Dict[str, int]:
    """Send every undelivered alert; failures are kept and retried (up to MAX_ATTEMPTS)."""
    sent = failed = skipped = 0
    pending = db.query(AlertEvent).filter(AlertEvent.delivered.is_(False), AlertEvent.attempts < MAX_ATTEMPTS).order_by(AlertEvent.created_at).all()
    for event in pending:
        if not notify.any_channel_configured():
            # Nowhere to send it: keep it visible in the Admin page and do not retry forever.
            event.delivered, event.delivery = True, "not sent: no e-mail or webhook configured"
            event.delivered_at = datetime.now(timezone.utc)
            skipped += 1
            continue
        results = notify.send_text(f"[Competitor Intel] {event.title}", event.body)
        event.attempts += 1
        if results and all(results.values()):
            event.delivered, event.delivered_at, event.delivery, event.last_error = True, datetime.now(timezone.utc), ", ".join(results), None
            sent += 1
        else:
            failed += 1
            event.last_error = "delivery failed on: " + ", ".join(k for k, ok in results.items() if not ok)
            if results and any(results.values()):          # at least one channel got it: do not keep re-sending to that one
                event.delivered, event.delivered_at = True, datetime.now(timezone.utc)
                event.delivery = "partial: " + ", ".join(k for k, ok in results.items() if ok)
    db.commit()
    return {"sent": sent, "failed": failed, "not_sent_no_channel": skipped}


def check_and_alert(db: Session, *, now: Optional[datetime] = None) -> Dict[str, int]:
    created = detect(db, now=now)
    db.commit()
    stats = deliver_pending(db)
    stats["new"] = len(created)
    return stats
