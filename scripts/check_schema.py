"""Is the database at the version this code needs?  Exit code 0 = yes, 1 = no (with what to do)."""
import sys

from app.services.schema_check import schema_status

if __name__ == "__main__":
    st = schema_status()
    print(("OK: " if st["ok"] else "PROBLEM: ") + st["message"])
    if not st["ok"]:
        print("  -> " + st["fix"])
    sys.exit(0 if st["ok"] else 1)
