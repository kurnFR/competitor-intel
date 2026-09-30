"""Weekly digest: what is new, what changed, what ends soon."""
from __future__ import annotations

import html
import logging
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Any, Dict, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, contains_eager

from app.core.config import settings
from app.models.entity import Brand, Competitor, Retailer
from app.models.promotion import Promotion
from app.models.promotion_change import PromotionChangeEvent
from app.services.channels import display_channel
from app.services.promotions.visibility import live_promotion_filter

logger = logging.getLogger(__name__)
LIMIT = 15


def _base_query(db: Session):
    return (
        db.query(Promotion)
        .outerjoin(Competitor, Promotion.competitor_id == Competitor.id)
        .outerjoin(Brand, Promotion.brand_id == Brand.id)
        .outerjoin(Retailer, Promotion.retailer_id == Retailer.id)
        .options(contains_eager(Promotion.competitor), contains_eager(Promotion.brand), contains_eager(Promotion.retailer))
    )


def _brief(p: Promotion) -> Dict[str, Any]:
    return {
        "id": str(p.id), "product": p.product_name, "brand": p.brand.name if p.brand else None,
        "competitor": p.competitor.name if p.competitor else None, "outlet": p.retailer.name if p.retailer else None,
        "channel": display_channel(p.channel, p.retailer.channel_type if p.retailer else None),
        "promotion_type": p.promotion_type, "promo_price": p.promo_price, "discount": p.discount_percentage,
        "valid_until": p.end_date.strftime("%Y-%m-%d") if p.end_date else None,
        "first_seen": p.first_seen_at.strftime("%Y-%m-%d") if p.first_seen_at else None,
    }


def build_digest(db: Session, *, days: int = 7, now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    live = live_promotion_filter(now, recency_days=90)

    new_q = _base_query(db).filter(live, Promotion.first_seen_at >= since)
    new_total = new_q.count()
    new_items = new_q.order_by(Promotion.rank_score.desc()).limit(LIMIT).all()

    ending_q = _base_query(db).filter(
        Promotion.status == "ACTIVE", Promotion.end_date.isnot(None),
        Promotion.end_date >= now, Promotion.end_date <= now + timedelta(days=7),
    )
    ending_total = ending_q.count()
    ending_items = ending_q.order_by(Promotion.end_date.asc(), Promotion.rank_score.desc()).limit(LIMIT).all()

    change_rows = (
        db.query(PromotionChangeEvent, Promotion)
        .join(Promotion, Promotion.id == PromotionChangeEvent.promotion_id)
        .outerjoin(Competitor, Promotion.competitor_id == Competitor.id)
        .options(contains_eager(Promotion.competitor))
        .filter(PromotionChangeEvent.observed_at >= since, PromotionChangeEvent.event_type != "CREATED")
        .order_by(PromotionChangeEvent.change_impact.desc(), PromotionChangeEvent.observed_at.desc())
    )
    change_total = change_rows.count()
    changes = [
        {"product": promo.product_name, "competitor": promo.competitor.name if promo.competitor else None,
         "event": ev.event_type, "field": ev.field_name, "previous": ev.previous_value, "new": ev.new_value,
         "observed_at": ev.observed_at.strftime("%Y-%m-%d")}
        for ev, promo in change_rows.limit(LIMIT).all()
    ]

    by_competitor = (
        db.query(Competitor.name, func.count(Promotion.id))
        .join(Promotion, Promotion.competitor_id == Competitor.id)
        .filter(live, Promotion.first_seen_at >= since)
        .group_by(Competitor.name).order_by(func.count(Promotion.id).desc()).limit(10).all()
    )
    return {
        "generated_at": now.isoformat(), "days": days,
        "summary": {"new": new_total, "changed": change_total, "ending_soon": ending_total},
        "new_promotions": [_brief(p) for p in new_items],
        "ending_soon": [_brief(p) for p in ending_items],
        "changes": changes,
        "new_by_competitor": [{"competitor": n, "count": c} for n, c in by_competitor],
    }


def _line(p: Dict[str, Any]) -> str:
    bits = [p.get("competitor") or p.get("brand") or "?", "-", p["product"], f"@ {p.get('outlet') or 'n/a'}"]
    if p.get("discount"):
        bits.append(f"({p['discount']:g}% off)")
    elif p.get("promo_price"):
        bits.append(f"(Rp{p['promo_price']:,.0f})")
    if p.get("valid_until"):
        bits.append(f"until {p['valid_until']}")
    return " ".join(bits)


def render_digest(d: Dict[str, Any]) -> tuple[str, str, str]:
    s = d["summary"]
    subject = f"Competitor promotions: {s['new']} new, {s['changed']} changed, {s['ending_soon']} ending soon"
    sections = [
        ("New promotions", [_line(p) for p in d["new_promotions"]], s["new"]),
        ("Changes to existing promotions", [
            f"{c.get('competitor') or '?'} - {c['product']}: {c['field'] or c['event']} {c['previous']} -> {c['new']}"
            for c in d["changes"]], s["changed"]),
        ("Ending within 7 days", [_line(p) for p in d["ending_soon"]], s["ending_soon"]),
    ]
    text_parts, html_parts = [subject, ""], [f"<h2>{html.escape(subject)}</h2>"]
    for title, lines, total in sections:
        text_parts.append(f"{title.upper()} ({total})")
        html_parts.append(f"<h3>{html.escape(title)} ({total})</h3><ul>")
        for line in lines or ["Nothing to report."]:
            text_parts.append(f"  * {line}")
            html_parts.append(f"<li>{html.escape(line)}</li>")
        if total > len(lines):
            text_parts.append(f"  ... and {total - len(lines)} more (see the dashboard)")
            html_parts.append(f"<li><em>... and {total - len(lines)} more (see the dashboard)</em></li>")
        text_parts.append("")
        html_parts.append("</ul>")
    return subject, "\n".join(text_parts), "\n".join(html_parts)


def digest_email_configured() -> bool:
    return bool(settings.SMTP_HOST and settings.digest_recipient_list and (settings.SMTP_FROM or settings.SMTP_USER))


def send_digest_email(db: Session, *, days: int = 7) -> bool:
    if not digest_email_configured():
        logger.info("Digest e-mail skipped: SMTP_HOST / DIGEST_RECIPIENTS / SMTP_FROM not configured.")
        return False
    subject, text, html_body = render_digest(build_digest(db, days=days))
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM or settings.SMTP_USER
    msg["To"] = ", ".join(settings.digest_recipient_list)
    msg.set_content(text)
    msg.add_alternative(html_body, subtype="html")
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30) as smtp:
        smtp.starttls(context=ssl.create_default_context())
        if settings.SMTP_USER:
            smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        smtp.send_message(msg)
    logger.info("Digest e-mail sent to %d recipient(s).", len(settings.digest_recipient_list))
    return True
