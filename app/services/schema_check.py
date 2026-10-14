"""Is the database at the version this code expects? One definition, used by startup, /health, the error pages and the checklist."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, FrozenSet, Optional

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings

UPGRADE_FIX = "Back up the database, then run:  alembic upgrade head   and restart the application."


@lru_cache(maxsize=1)
def expected_heads() -> FrozenSet[str]:
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    return frozenset(ScriptDirectory.from_config(config).get_heads())


def _current_heads(engine: Engine) -> FrozenSet[str]:
    with engine.connect() as conn:
        context = MigrationContext.configure(conn, opts={"version_table_schema": settings.DATABASE_SCHEMA})
        return frozenset(context.get_current_heads())


def schema_status(engine: Optional[Engine] = None) -> Dict[str, Any]:
    """{'ok': bool, 'problem': None|'database_unreachable'|'schema_not_set_up'|'schema_outdated'|'schema_newer', 'message', 'fix', ...}"""
    if engine is None:
        from app.db.session import engine as default_engine
        engine = default_engine
    expected = sorted(expected_heads())
    try:
        current = sorted(_current_heads(engine))
    except SQLAlchemyError:
        return {"ok": False, "problem": "database_unreachable", "expected": expected, "current": [],
                "message": "The application cannot reach the database.",
                "fix": "Check that PostgreSQL is running and that DATABASE_URL in .env is correct."}
    if current == expected:
        return {"ok": True, "problem": None, "expected": expected, "current": current, "message": "Database is up to date.", "fix": ""}
    if not current:
        return {"ok": False, "problem": "schema_not_set_up", "expected": expected, "current": current,
                "message": "The database has not been set up yet.", "fix": "Run:  alembic upgrade head   and restart the application."}
    known = _known_revisions()
    if any(rev not in known for rev in current):
        return {"ok": False, "problem": "schema_newer", "expected": expected, "current": current,
                "message": "The database is newer than this version of the application.",
                "fix": "Update the application code (git pull) or restore the database from a backup."}
    return {"ok": False, "problem": "schema_outdated", "expected": expected, "current": current,
            "message": f"The database is out of date for this version of the application (it is at {', '.join(current)}; "
                       f"this version needs {', '.join(expected)}).",
            "fix": UPGRADE_FIX}


@lru_cache(maxsize=1)
def _known_revisions() -> FrozenSet[str]:
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    return frozenset(r.revision for r in ScriptDirectory.from_config(config).walk_revisions())
