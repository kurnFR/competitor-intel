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
- Never treat a newly discovered source as trusted until assessed and approved.
- Never bypass source access controls.

## 3. Startup Checklist

1. PostgreSQL reachable.
2. Database `competitor_intel` exists.
3. Application schema exists.
4. `alembic upgrade head` succeeds.
5. Required environment variables are present.
6. LLM gateway is reachable if extraction is enabled.
7. Source registry contains intended active sources.
8. Approved URL targets exist or discovery is ready.
9. No unexpected access to `dwh_prod` is configured.

## 4. Migration

```bash
alembic upgrade head
alembic current
```

## 5. Seed

```bash
PYTHONPATH=. python3 scripts/seed_data.py
```

Seed scripts must be idempotent.

## 6. Source Registry Operations

The source registry is the control plane for crawling.

For each source verify:

```text
name
domain
source_type
reliability
priority
adapter
access_status
is_active
crawl frequency
```

For each URL target verify:

```text
url
page type
priority
is_active
next_crawl_at
last success
failure/backoff state
```

Disabling a source or URL must not delete historical observations.

## 7. Discover Sources

Source discovery is separate from scheduled crawling.

Discovery may use permitted public search, sitemaps, feeds and source navigation to find candidate domains and URLs.

A candidate must be assessed before activation.

Recommended workflow:

```text
Discover
  -> Candidate
  -> Assess relevance/access
  -> Configure adapter
  -> Test extraction/evidence
  -> Approve
  -> Activate
```

Never automatically promote every search result to an active source.

## 8. Run Pipeline

```bash
PYTHONPATH=. python3 scripts/run_pipeline.py
```

A successful cycle should produce, as applicable:

```text
source/url target
  -> crawl job
  -> document
  -> change detection
  -> extraction run
  -> observation
  -> validation
  -> geography normalization
  -> entity resolution
  -> canonical promotion/review
```

An unchanged document may skip expensive AI extraction when the source adapter determines that the content is safely unchanged.

## 9. Scan vs Discover

`Scan now` means crawl active approved targets.

`Discover sources` means find candidate sources/URLs for assessment.

Do not confuse discovery with production collection.

## 10. Dashboard Data Check

If the dashboard shows a promotion, verify:

1. it exists in PostgreSQL
2. API returns it
3. it has evidence
4. status is eligible
5. `last_verified_at` is appropriate
6. geography is present and correct
7. source is approved/active

The UI must never be the only place where a promotion exists.

## 11. Empty Database Behavior

An empty database is valid.

```text
No active promotions found.
Run Scan now to collect source data.
```

Never display demo rows.

## 12. Source Failure

If a source fails:

- record the failed crawl job
- retain previous successful data
- expose health as failed/stale
- retry with bounded backoff
- do not delete existing promotions merely because the source is temporarily unavailable

A successful crawl returning zero promotions is still a successful crawl.

## 13. Source Health

```text
HEALTHY = recent successful crawl
WARNING  = recent failures but usable successful data exists
STALE    = no recent successful crawl
FAILED   = current crawl failed
BLOCKED  = source access blocked/restricted
NOT_RUN  = no crawl completed yet
```

Exact thresholds are configuration.

## 14. Crawler Troubleshooting

Check:

- HTTP status
- response type
- robots/terms/access compliance
- page structure
- source URL changes
- parser/selector fixtures
- extraction counts
- content hash/change detection
- geography text extraction
- retailer/channel extraction

Every source adapter should have regression fixtures for representative pages.

## 15. LLM Troubleshooting

Check:

- gateway availability
- model
- credentials
- structured output validity
- prompt/schema version
- timeout/token limits

If extraction fails, preserve the source document and mark extraction failed. Do not create a fallback promotion from imagination.

## 16. PostgreSQL Troubleshooting

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

The application should fail clearly if PostgreSQL is unavailable.

## 17. Stale Data

If data is stale:

1. check source health
2. check latest successful crawl
3. inspect crawl jobs
4. inspect extraction failures
5. inspect scheduler
6. inspect URL target `next_crawl_at`
7. run controlled Scan now

Never manually alter timestamps to fake freshness.

## 18. Incorrect Geography

If a promotion is shown as nationwide but the source says regional:

1. inspect original crawl document
2. inspect observation
3. inspect geography extraction
4. inspect normalization mapping
5. inspect canonical promotion
6. correct pipeline/mapping
7. preserve original evidence
8. add regression test

Do not solve this only in frontend code.

## 19. Duplicate / Regional Merge Bug

If two activities were incorrectly merged:

1. identify observations
2. compare product, retailer, channel, price, mechanic, validity and geography
3. split canonical records if commercially material
4. preserve historical observations
5. fix matching rules
6. add regression test

## 20. Multi-Source Conflict

When sources disagree:

```text
retain observations
    ↓
compare timestamp
    ↓
compare source reliability
    ↓
compare retailer/channel
    ↓
compare geography
    ↓
determine same vs different activity
    ↓
review if material conflict remains
```

Never silently overwrite one source with another.

## 21. Expired Promotion Appears Active

Check source end date, timezone conversion, `end_date`, status calculation, freshness, API filter and frontend cache.

An explicit expired end date always wins over a recent crawl.

## 22. Backoff and Blocking

Repeated failures must increase retry delay. A blocked source must not trigger infinite retries or access-control bypass attempts.

After configured failure thresholds, mark the source/URL `BLOCKED` or `STALE` and create an operational review item.

## 23. Backup

Back up at minimum:

- canonical promotions
- observations
- evidence metadata
- source registry
- source URL registry
- review queue
- master data

Large raw documents require their own durable storage backup policy.

## 24. Deployment Safety

Before deployment:

1. review migrations
2. back up database
3. run tests
4. deploy
5. health check
6. verify API
7. verify one approved source crawl
8. verify dashboard data
9. verify source health

## 25. Security Incident

If a credential is committed:

1. revoke/rotate immediately
2. remove from active configuration
3. clean history if required
4. inspect access logs
5. issue new secret through secure configuration

Deleting the file alone is insufficient.

## 26. Production Verification

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/promotions/top10
curl http://localhost:8000/api/v1/stats/
```

Also verify the database directly for a sample promotion and its evidence/source rows.

## 27. Definition of Healthy System

A healthy system means:

- PostgreSQL reachable
- scheduler running
- approved sources configured
- URL registry populated
- source discovery observable
- crawls succeeding within expected thresholds
- extraction succeeding within expected thresholds
- evidence coverage high
- geography resolution healthy
- review queue observable
- active data fresh
- Top 10 contains only eligible records
- dashboard/API/PostgreSQL agree
