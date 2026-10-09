import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

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
