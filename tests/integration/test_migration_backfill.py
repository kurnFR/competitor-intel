"""Promotions must end up linked to their source after upgrading, whichever way the link can be recovered."""
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import settings

ROOT = Path(__file__).resolve().parents[2]
BEFORE_PRD = "d3e4f5a6b701"          # the schema before promotions.source_id existed
BEFORE_BACKFILL = "g6b7c8d9e012"


_FILL = {"text": "'x'", "character varying": "'x'", "integer": "0", "bigint": "0", "boolean": "true", "double precision": "0.5", "real": "0.5",
         "numeric": "0", "uuid": "gen_random_uuid()", "jsonb": "'{}'::jsonb", "json": "'{}'::json"}


def insert(conn, table, **values):
    """INSERT that also fills every other required (NOT NULL, no default) column with a neutral value, so these tests do
    not depend on the exact layout of the old schema."""
    cols = conn.execute(text("SELECT column_name, data_type FROM information_schema.columns WHERE table_schema='competitor_intel' AND table_name=:t "
                             "AND is_nullable='NO' AND column_default IS NULL"), {"t": table}).all()
    names, exprs = list(values), [f":{k}" for k in values]
    for name, dtype in cols:
        if name in values:
            continue
        names.append(name)
        exprs.append("now()" if dtype.startswith("timestamp") else _FILL.get(dtype, "'x'"))
    conn.execute(text(f"INSERT INTO competitor_intel.{table} ({', '.join(names)}) VALUES ({', '.join(exprs)})"), values)


@pytest.fixture()
def scratch():
    base = make_url(settings.DATABASE_URL_ADMIN)
    name = f"zz_mig_{uuid.uuid4().hex[:8]}"
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
    except Exception as exc:
        pytest.skip(f"cannot create a scratch database here: {exc}")
    url = base.set(database=name)
    env = {**os.environ, "DATABASE_URL": url.render_as_string(hide_password=False), "DATABASE_URL_ADMIN": url.render_as_string(hide_password=False),
           "PYTHONPATH": str(ROOT)}

    def alembic(*args):
        done = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=ROOT, env=env, capture_output=True, text=True)
        assert done.returncode == 0, done.stderr[-400:]

    yield type("S", (), dict(alembic=staticmethod(alembic), engine=create_engine(url)))
    admin_conn = admin.connect()
    admin_conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    admin_conn.close()
    admin.dispose()


def test_promotions_get_their_source_from_observations_or_from_evidence(scratch):
    """Old data: one promotion has an observation, one only has evidence, one has neither."""
    scratch.alembic("upgrade", BEFORE_PRD)
    ids = {k: uuid.uuid4() for k in ("source", "doc", "p_obs", "p_ev", "p_none")}
    with scratch.engine.begin() as c:
        insert(c, "source_registry", id=ids["source"], name="S", domain="s.example", base_url="https://s.example/", source_type="RETAILER")
        insert(c, "crawl_documents", id=ids["doc"], source_id=ids["source"], url="https://s.example/p", content_hash=uuid.uuid4().hex * 2)
        for key in ("p_obs", "p_ev", "p_none"):
            insert(c, "promotions", id=ids[key], product_name=key, geography="Indonesia")
        insert(c, "promotion_observations", id=uuid.uuid4(), promotion_id=ids["p_obs"], document_id=ids["doc"])
        insert(c, "promotion_evidence", id=uuid.uuid4(), promotion_id=ids["p_ev"], document_id=ids["doc"], evidence_text="quote")

    scratch.alembic("upgrade", "head")
    with scratch.engine.connect() as c:
        rows = {r[0]: (r[1], r[2], r[3]) for r in c.execute(text("SELECT product_name, source_id, geography, geography_region FROM competitor_intel.promotions"))}
    assert rows["p_obs"][0] == ids["source"]                  # recovered from the observation
    assert rows["p_ev"][0] == ids["source"]                   # recovered from the evidence alone
    assert rows["p_none"][0] is None                          # nothing links it: stays hidden rather than guessed
    assert rows["p_obs"][1:] == (None, "UNKNOWN")             # the old fabricated "Indonesia" is gone


def test_the_backfill_revision_is_safe_to_repeat_and_fixes_databases_that_missed_it(scratch):
    scratch.alembic("upgrade", BEFORE_BACKFILL)               # a database that already ran the earlier version of the PRD migration
    sid, did, pid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    with scratch.engine.begin() as c:
        insert(c, "source_registry", id=sid, name="S2", domain="s2.example", base_url="https://s2.example/", source_type="RETAILER")
        insert(c, "crawl_documents", id=did, source_id=sid, url="https://s2.example/p", content_hash=uuid.uuid4().hex * 2)
        insert(c, "promotions", id=pid, product_name="late")
        insert(c, "promotion_evidence", id=uuid.uuid4(), promotion_id=pid, document_id=did, evidence_text="q")
    with scratch.engine.connect() as c:
        assert c.execute(text("SELECT source_id FROM competitor_intel.promotions WHERE id = :p"), {"p": pid}).scalar() is None
    scratch.alembic("upgrade", "head")
    with scratch.engine.connect() as c:
        assert c.execute(text("SELECT source_id FROM competitor_intel.promotions WHERE id = :p"), {"p": pid}).scalar() == sid
    scratch.alembic("downgrade", BEFORE_BACKFILL)             # the data step has no undo, but going back and forth must not fail
    scratch.alembic("upgrade", "head")
