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

    # Detect commercial & marketing intelligence alerts (price shocks, disruptive mechanics, undercuts)
    created.extend(_detect_commercial_alerts(db, now))
    return created


def _detect_commercial_alerts(db: Session, now: datetime) -> List[AlertEvent]:
    from sqlalchemy import cast, String, select
    from app.core.config import settings
    from app.models.entity import Competitor, Retailer
    from app.models.promotion import Promotion
    from app.services.comparison import build_comparison
    from app.services.promotions.visibility import live_promotion_filter

    created: List[AlertEvent] = []
    live_filter = live_promotion_filter(now, recency_days=settings.RECENCY_MONTHS * 30)

    # 1. Price Shock: competitor discounts >= threshold (default 20%)
    shock_threshold = getattr(settings, "ALERT_PRICE_SHOCK_DISCOUNT_PCT", 20.0)
    if shock_threshold and shock_threshold > 0:
        already_alerted_price_shocks = (
            select(AlertEvent.subject_id)
            .filter(AlertEvent.kind == "PRICE_SHOCK", AlertEvent.subject_id.isnot(None))
        )
        deep_promos = (
            db.query(Promotion)
            .outerjoin(Competitor, Promotion.competitor_id == Competitor.id)
            .outerjoin(Retailer, Promotion.retailer_id == Retailer.id)
            .filter(
                live_filter,
                Promotion.discount_percentage >= shock_threshold,
                ~cast(Promotion.id, String).in_(already_alerted_price_shocks),
            )
            .order_by(Promotion.last_seen_at.desc(), Promotion.id.desc())
            .limit(50)
            .all()
        )
        for p in deep_promos:
            comp_name = p.competitor.name if p.competitor else "Competitor"
            disc = round(p.discount_percentage or 0)
            fp = f"price-shock:{p.id}:{disc}"
            title = f"🚨 Price Shock: {comp_name} - {p.product_name} ({disc}% off)"
            reg_fmt = f"Rp {p.regular_price:,.0f}" if p.regular_price else "N/A"
            promo_fmt = f"Rp {p.promo_price:,.0f}" if p.promo_price else "N/A"
            ret_name = p.retailer.name if p.retailer else "Modern Trade"
            ev_quote = (p.evidence_items[0].evidence_text or "") if p.evidence_items else "N/A"
            body = (
                f"Competitor {comp_name} launched a deep discount of {disc}% on {p.product_name}.\n"
                f"Category: {p.category} | Outlet: {ret_name} | Region: {p.geography_region}\n"
                f"Regular: {reg_fmt} -> Promo: {promo_fmt}\n"
                f"Dates: {p.start_date.strftime('%Y-%m-%d') if p.start_date else 'N/A'} to {p.end_date.strftime('%Y-%m-%d') if p.end_date else 'N/A'}\n"
                f"Evidence: \"{ev_quote}\""
            )
            e = _raise(db, kind="PRICE_SHOCK", fingerprint=fp, subject_id=str(p.id), title=title, body=body)
            if e:
                created.append(e)

    # 2. Disruptive Promotion: BOGO (BUY_X_GET_Y)
    if getattr(settings, "ALERT_DISRUPTIVE_PROMOS", True):
        already_alerted_bogo = (
            select(AlertEvent.subject_id)
            .filter(AlertEvent.kind == "DISRUPTIVE_PROMO", AlertEvent.subject_id.isnot(None))
        )
        bogo_promos = (
            db.query(Promotion)
            .outerjoin(Competitor, Promotion.competitor_id == Competitor.id)
            .outerjoin(Retailer, Promotion.retailer_id == Retailer.id)
            .filter(
                live_filter,
                Promotion.promotion_type == "BUY_X_GET_Y",
                ~cast(Promotion.id, String).in_(already_alerted_bogo),
            )
            .order_by(Promotion.last_seen_at.desc(), Promotion.id.desc())
            .limit(50)
            .all()
        )
        for p in bogo_promos:
            comp_name = p.competitor.name if p.competitor else "Competitor"
            buy_q = p.buy_quantity or 1
            free_q = p.free_quantity or 1
            fp = f"disruptive-promo:{p.id}:bogo:{buy_q}x{free_q}"
            title = f"⚡ Disruptive Promo: {comp_name} (Buy {buy_q} Get {free_q}) - {p.product_name}"
            price_val = p.promo_price or p.regular_price
            price_fmt = f"Rp {price_val:,.0f}" if price_val else "N/A"
            ret_name = p.retailer.name if p.retailer else "Modern Trade"
            ev_quote = (p.evidence_items[0].evidence_text or "") if p.evidence_items else "N/A"
            body = (
                f"Competitor {comp_name} launched a Buy {buy_q} Get {free_q} promotion on {p.product_name}.\n"
                f"Category: {p.category} | Outlet: {ret_name} | Pack Size: {p.pack_size or 'N/A'}\n"
                f"Price: {price_fmt}\n"
                f"Dates: {p.start_date.strftime('%Y-%m-%d') if p.start_date else 'N/A'} to {p.end_date.strftime('%Y-%m-%d') if p.end_date else 'N/A'}\n"
                f"Evidence: \"{ev_quote}\""
            )
            e = _raise(db, kind="DISRUPTIVE_PROMO", fingerprint=fp, subject_id=str(p.id), title=title, body=body)
            if e:
                created.append(e)

    # 3. Competitive Undercut Alerts: competitor price per 100g undercuts our product
    undercut_threshold = getattr(settings, "ALERT_UNDERCUT_GAP_PCT", -15.0)
    try:
        comparison = build_comparison(db, now=now)
        for own_item in comparison.get("products", []):
            if own_item.get("price_per_100g") is None:
                continue
            for comp in own_item.get("comparable", []):
                gap = comp.get("gap_pct")
                if gap is not None and gap <= undercut_threshold:
                    gap_abs = abs(round(gap))
                    fp = f"competitor-undercut:{own_item['id']}:{comp['promotion_id']}:{gap_abs}"
                    title = f"⚠️ Price Undercut: {comp['competitor'] or 'Competitor'} undercuts {own_item['name']} by {gap_abs}%"
                    body = (
                        f"Competitor promotion significantly undercuts our product {own_item['name']} on a normalized per-100g basis.\n"
                        f"Our Product: {own_item['name']} ({own_item.get('pack_size') or 'N/A'}) @ Rp {own_item['regular_price']:,.0f} -> Rp {own_item['price_per_100g']}/100g\n"
                        f"Competitor SKU: {comp['product']} ({comp.get('competitor') or 'N/A'}) @ Rp {comp.get('effective_pack_price', 0):,.0f} -> Rp {comp['price_per_100g']}/100g\n"
                        f"Price Gap: {gap}% ({gap_abs}% cheaper per 100g)\n"
                        f"Outlet: {comp.get('outlet') or 'Modern Trade'} | Valid Until: {comp.get('valid_until') or 'N/A'}"
                    )
                    e = _raise(db, kind="COMPETITOR_UNDERCUT", fingerprint=fp, subject_id=comp["promotion_id"], title=title, body=body)
                    if e:
                        created.append(e)
    except Exception as exc:
        logger.warning("Could not compute comparison for undercut alerts: %s", exc)

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
