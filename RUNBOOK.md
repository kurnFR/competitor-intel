# RUNBOOK.md — Operations and Troubleshooting

## 1. Purpose

Operational guide for running the competitor intelligence platform against the existing PostgreSQL server.

## 2. Golden Rules

- PostgreSQL `competitor_intel` is the application source of truth.
- `dwh_prod` is out of scope.
- Never put secrets in Git.
- Never interpret crawler failure as zero promotions.
- Never manually edit canonical records without preserving audit history.
- Never bypass evidence and validation to make the dashboard look complete.

## 3. Startup Checklist

1. PostgreSQL reachable.
2. Database `competitor_intel` exists.
3. Application schema exists.
4. `alembic upgrade head` succeeds.
5. Required environment variables are present.
6. LLM gateway is reachable if extraction is enabled.
7. Source registry contains active sources.
8. No unexpected access to `dwh_prod` is configured.

## 4. Migration

```bash
alembic upgrade head
```

Verify migration status:

```bash
alembic current
```

## 5. Seed

```bash
PYTHONPATH=. python3 scripts/seed_data.py
```

Seed scripts must be idempotent.

## 6. Run Pipeline

```bash
PYTHONPATH=. python3 scripts/run_pipeline.py
```

A successful run should produce:

```text
crawl job
  -> document
  -> extraction run
  -> observation
  -> validation
  -> canonical promotion/review
```

## 7. Dashboard Data Check

If the dashboard shows a promotion, verify:

1. it exists in PostgreSQL
2. the API returns it
3. it has evidence
4. its status is eligible
5. its `last_verified_at` is appropriate
6. its geography is present and correct

The UI must never be the only place where a promotion exists.

## 8. Empty Database Behavior

An empty database is valid.

The UI must show:

```text
No active promotions found.
Run Scan now to collect source data.
```

It must not display demo rows.

## 9. Source Failure

If a source fails:

- record a failed crawl job
- retain the previous successful data
- expose source health as failed/stale
- retry according to policy
- do not delete existing promotions merely because the source is temporarily unavailable

## 10. Hemat.id Troubleshooting

Check:

- HTTP status
- response content type
- page structure
- robots/terms compliance
- source URL changes
- HTML selector/fixture tests
- parser extraction counts
- geographic text extraction

A parser update must include a fixture regression test.

## 11. LLM Troubleshooting

Check:

- gateway availability
- model name
- API credentials
- structured output validity
- prompt/schema version
- timeout
- token/response limits

If AI extraction fails, preserve the source document and mark the extraction as failed. Do not invent a fallback promotion.

## 12. PostgreSQL Troubleshooting

Check:

```text
host
port
DB name = competitor_intel
schema = competitor_intel
role permissions
connection pool
migration version
```

The application should fail clearly if the configured database is unavailable.

## 13. Stale Data

If the UI reports stale data:

1. check source health
2. check latest successful crawl
3. inspect crawl jobs
4. inspect extraction failures
5. inspect scheduler process
6. run a controlled `Scan now`

Do not manually change timestamps to make records appear fresh.

## 14. Incorrect Geography

If a promotion is shown as nationwide but the source says a regional scope:

1. inspect the original crawl document
2. inspect promotion observation
3. inspect geography normalization
4. inspect canonical promotion
5. correct the normalization/mapping
6. preserve the original evidence
7. add a regression test

The correct fix is in the ingestion/model pipeline, not a frontend display patch.

## 15. Duplicate Promotions

If two regional activities were incorrectly merged:

1. identify the source observations
2. compare product, retailer, price, mechanic and geography
3. split canonical records if commercially material
4. preserve historical observations
5. fix matching rules
6. add a regression test

## 16. Expired Promotion Appears Active

Check:

- source end date
- timezone conversion
- `end_date`
- status calculation
- last verification
- API active filter
- frontend cache

Never solve this by deleting the record; historical evidence should remain available.

## 17. Source Health Semantics

```text
HEALTHY  = recent successful crawl
WARNING  = recent failures but successful data exists
STALE    = no recent successful crawl
FAILED   = current crawl failed
BLOCKED  = source blocked collection
```

Exact thresholds are configuration.

## 18. Backup

PostgreSQL backups are an infrastructure responsibility. At minimum back up:

- canonical promotions
- observations
- evidence metadata
- source registry
- review queue
- master data

Raw large documents should have their own durable storage backup policy.

## 19. Deployment Safety

Before deployment:

1. review migration
2. back up database
3. run tests
4. deploy application
5. run health check
6. verify API
7. verify one real source crawl
8. verify dashboard data

## 20. Security Incident

If a credential is committed:

1. revoke/rotate immediately
2. remove it from active configuration
3. clean Git history if required by security policy
4. inspect access logs
5. issue a new secret through secure configuration

Do not rely on deleting the file alone.

## 21. Production Verification Commands

Health:

```bash
curl http://localhost:8000/health
```

Top 10:

```bash
curl http://localhost:8000/api/v1/promotions/top10
```

Stats:

```bash
curl http://localhost:8000/api/v1/stats/
```

## 22. Definition of Healthy System

A healthy system means:

- PostgreSQL reachable
- scheduler running
- configured sources producing successful crawls
- extraction succeeding within expected threshold
- evidence coverage high
- review queue observable
- active data fresh
- Top 10 query returns only eligible records
- dashboard and API agree with PostgreSQL
