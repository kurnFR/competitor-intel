"""Outgoing notifications: e-mail and chat webhook. Shared by the weekly digest and the failure alerts."""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from typing import Dict, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


def email_configured() -> bool:
    return bool(settings.SMTP_HOST and settings.digest_recipient_list and (settings.SMTP_FROM or settings.SMTP_USER))


def webhook_configured() -> bool:
    return settings.DIGEST_WEBHOOK_URL.lower().startswith("https://")


def any_channel_configured() -> bool:
    return email_configured() or webhook_configured()


def send_email(subject: str, text: str, html: Optional[str] = None) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM or settings.SMTP_USER
    msg["To"] = ", ".join(settings.digest_recipient_list)
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30) as smtp:
        smtp.starttls(context=ssl.create_default_context())
        if settings.SMTP_USER:
            smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        smtp.send_message(msg)
    logger.info("E-mail sent to %d recipient(s): %s", len(settings.digest_recipient_list), subject)


def send_webhook(text: str, limit: int = 3500) -> None:
    import httpx
    if len(text) > limit:
        text = text[:limit].rsplit("\n", 1)[0] + "\n... (truncated)"
    resp = httpx.post(settings.DIGEST_WEBHOOK_URL, json={"text": text}, timeout=15.0, follow_redirects=False)
    resp.raise_for_status()
    logger.info("Message posted to webhook.")


def send_text(subject: str, body: str) -> Dict[str, bool]:
    """Send to every configured channel; one channel failing never stops the other. Returns channel -> delivered."""
    results: Dict[str, bool] = {}
    if email_configured():
        try:
            send_email(subject, body)
            results["email"] = True
        except Exception:
            logger.exception("E-mail notification failed")
            results["email"] = False
    if webhook_configured():
        try:
            send_webhook(f"{subject}\n{body}")
            results["webhook"] = True
        except Exception:
            logger.exception("Webhook notification failed")
            results["webhook"] = False
    return results
