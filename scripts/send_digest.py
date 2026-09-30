"""Send the promotion digest now (also runs weekly from the scheduler) via e-mail and/or webhook."""
import sys

from app.db.session import SessionLocal
from app.services.digest import digest_configured, send_digest

if __name__ == "__main__":
    if not digest_configured():
        print("Set SMTP_HOST + SMTP_FROM + DIGEST_RECIPIENTS and/or DIGEST_WEBHOOK_URL (https) first.", file=sys.stderr)
        sys.exit(1)
    db = SessionLocal()
    try:
        results = send_digest(db)
    finally:
        db.close()
    print(results)
    sys.exit(0 if any(results.values()) else 1)
