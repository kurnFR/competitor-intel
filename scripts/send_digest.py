"""Send the promotion digest e-mail now (also runs weekly from the scheduler)."""
import sys

from app.db.session import SessionLocal
from app.services.digest import digest_email_configured, send_digest_email

if __name__ == "__main__":
    if not digest_email_configured():
        print("Set SMTP_HOST, SMTP_FROM and DIGEST_RECIPIENTS first.", file=sys.stderr)
        sys.exit(1)
    db = SessionLocal()
    try:
        send_digest_email(db)
    finally:
        db.close()
