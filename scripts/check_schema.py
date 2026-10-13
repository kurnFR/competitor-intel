"""Is the database at the version this code needs?  Exit code 0 = yes, 1 = no (with what to do)."""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.services.schema_check import schema_status  # noqa: E402


def main() -> int:
    st = schema_status()
    print(("OK: " if st["ok"] else "PROBLEM: ") + st["message"])
    if not st["ok"]:
        print("  -> " + st["fix"])
    return 0 if st["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
