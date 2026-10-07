"""Apply the data-retention policy now (it also runs daily from the scheduler).

    python -m scripts.retention --dry-run     # show what would be removed, change nothing
    python -m scripts.retention               # do it
"""
import sys

from app.core.config import settings
from app.db.session import SessionLocal
from app.services.retention import document_days, run_retention


def human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n} B"


def main() -> int:
    dry = "--dry-run" in sys.argv
    db = SessionLocal()
    try:
        r = run_retention(db, dry_run=dry)
    finally:
        db.close()
    print(("DRY RUN - nothing changed.\n" if dry else "") + f"Policy: crawled pages older than {document_days()} days (except the newest of each website), "
          f"audit log {settings.RETENTION_AUDIT_DAYS} d, scan history {settings.RETENTION_SCAN_RUN_DAYS} d, alerts {settings.RETENTION_ALERT_DAYS} d.")
    print(f"  crawled pages trimmed : {r['documents_trimmed']}  ({r['raw_files_removed']} raw files, {human(r['bytes_freed'])}, "
          f"{r['text_characters_freed']:,} text characters)")
    print(f"  audit log rows        : {r['audit_log_rows']}\n  scan history rows     : {r['scan_runs']}\n  alert rows            : {r['alert_events']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
