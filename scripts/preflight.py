"""Check that this installation is set up correctly.

    python -m scripts.preflight           # configuration, database, sources, scans
    python -m scripts.preflight --llm     # also test the connection to the LLM

Exit code 1 if any check FAILS (so it can gate a deployment). WARN = worth fixing, INFO = for your information.
"""
import sys

from app.db.session import SessionLocal
from app.services.preflight import FAIL, INFO, PASS, WARN, run_checks, summarize

ICON = {PASS: "[ OK ]", WARN: "[WARN]", FAIL: "[FAIL]", INFO: "[INFO]"}


def main() -> int:
    db = SessionLocal()
    try:
        checks = run_checks(db, check_llm="--llm" in sys.argv)
    finally:
        db.close()
    for c in checks:
        print(f"{ICON[c.status]} {c.name}: {c.detail}")
        if c.fix and c.status in (WARN, FAIL, INFO):
            print(f"         -> {c.fix}")
    s = summarize(checks)
    print(f"\n{s[PASS]} ok, {s[WARN]} warning(s), {s[FAIL]} failure(s), {s[INFO]} note(s).  "
          + ("Ready to use." if s["ready"] else "Fix the failures above first."))
    return 0 if s["ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
