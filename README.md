# FMCG Competitor Promotion Intelligence Platform

AI-powered competitive promotion intelligence for the Indonesian FMCG snack market, initially focused on biscuits, crackers, cookies and wafers.

> **Documentation freeze:** These documents define the requirements that implementation must follow. Do not add mock promotion data or silently invent missing commercial facts.

## What the system does

The platform discovers and monitors multiple public sources that may contain competitor product, price and promotion information. It converts source content into structured observations, validates the facts, resolves entities, preserves geography, deduplicates without losing regional differences, and exposes trusted data to the UI.

Hemat.id is an initial source, **not the only source** and not the permanent source of truth.

Candidate source classes include official company/brand sites, retailer and modern-trade sites, local retailers, verified marketplace stores, public e-commerce pages, promotion aggregators and established news/media. Collection is only performed where public access and applicable rules permit it.

See [`SOURCE_STRATEGY.md`](SOURCE_STRATEGY.md).

## Source of Truth

The **PostgreSQL database is the source of truth for the UI**. The dashboard must query the API, and the API must query PostgreSQL. The UI must never use hard-coded promotion rows, demo JSON, or generated fallback records.

The application may reuse the customer's existing PostgreSQL server, but the application database is isolated from unrelated DWH data.

```text
competitor_intel database
competitor_intel schema
```

The application must not read or modify `dwh_prod` unless a future approved integration explicitly changes this requirement.

## Source Registry and Continuous Discovery

The system has a persistent source/URL registry.

```text
Discovery
   ↓
Candidate source / URL
   ↓
Assessment
   ↓
Approved
   ↓
Scheduled crawling
   ↓
Evidence + observations
```

Normal scheduled runs should primarily crawl **approved sources and URL targets already stored in PostgreSQL**. The system should not restart from an unrestricted web search on every run.

A separate discovery process periodically searches for new candidate sources and relevant pages. Discovery results must be assessed before they become trusted production sources.

The registry stores source type, priority, reliability, crawl frequency, adapter, access status and health. URL targets can have their own priority and frequency.

## What the system answers

> What are the 10 most commercially important competitor promotions that are currently active, recently verified, geographically understood, and supported by reliable source evidence?

Every displayed promotion must be traceable to:

- source URL/domain
- crawl/retrieval timestamp
- evidence
- extracted fields
- geographic scope and exclusions
- retailer/channel scope
- validity period
- validation result
- AI confidence
- canonical product/brand/competitor mapping

## Critical Business Rules

### Geography

Geography is first-class data. Preserve exact source wording and normalized inclusion/exclusion scopes.

Never default unknown geography to Indonesia.

### Regional price

The same SKU can have different prices or mechanics by Java, Sumatera, Kalimantan, Sulawesi, Bali or another commercial scope. Materially different observations must not be merged.

### Evidence

No evidence = not verified. Unknown competitor/product/price/date/geography values remain unknown and may enter review.

### Freshness

Track separately:

- `first_seen_at`
- `last_seen_at`
- `last_verified_at`

Default active Top 10 freshness is 90 days, but a recently crawled expired promotion remains expired.

### Quality before ranking

Ranking occurs only after validity, freshness, evidence, identity and geography quality checks.

## Architecture

```text
Public Web Sources
       |
       v
Source Discovery -----> Source/URL Registry
                              |
                              v
                         Scheduler
                              |
                              v
                     Crawler / Browser
                              |
                              v
                    Raw Crawl Documents
                              |
                              v
                     Change Detection
                              |
                    changed? / unchanged
                              |
                              v
                     AI Extraction
                              |
                              v
               Validation + Geography
                              |
                              v
                    Entity Resolution
                              |
                              v
                    Dedup / Matching
                              |
                              v
                        Quality Gate
                         /        \
                       PASS      REVIEW
                        |           |
                        v           v
                    PostgreSQL   Review Queue
                        |
                        v
                       API
                        |
                        v
                       UI
```

## PostgreSQL Data Model

The main layers are:

1. Source registry and crawl jobs
2. Raw crawl documents
3. AI extraction observations
4. Master entities
5. Canonical promotions
6. Geography inclusions/exclusions
7. Evidence and validation
8. Review queue
9. Analytics/ranking

See [`DATA_MODEL.md`](DATA_MODEL.md).

## UI / UX

Recommended enterprise navigation:

```text
Overview
Promotions
Regional Pricing
Competitors
Sources
Review Queue
Settings
```

The main workflow uses a filterable promotion table plus a right-side detail drawer. The drawer exposes price, mechanic, retailer, geography, validity, evidence, source, verification timestamp and field-level confidence.

See [`UI_UX_DESIGN.md`](UI_UX_DESIGN.md).

## Documentation Set

| Document | Purpose |
|---|---|
| `README.md` | Project overview, setup and operating principles |
| `FMCG Competitor Promotion.md` | Product requirements / PRD |
| `TECHNICAL_DESIGN.md` | Technical architecture and implementation requirements |
| `SOURCE_STRATEGY.md` | Multi-source discovery, registry, crawling and conflict strategy |
| `DATA_MODEL.md` | PostgreSQL entities, relationships and integrity rules |
| `DATA_QUALITY.md` | Validation, provenance, freshness and trust rules |
| `UI_UX_DESIGN.md` | Professional dashboard UX and interaction requirements |
| `RUNBOOK.md` | Operational procedures, troubleshooting and production checks |

## Setup

### Prerequisites

- Python 3.12+
- PostgreSQL 12+ on the existing PostgreSQL server
- `pg_trgm` extension
- configured LLM gateway for AI extraction
- optional Playwright/Tesseract/PDF tooling according to source needs

### Environment

Copy `.env.example` to `.env` and configure the `competitor_intel` database only.

```env
DATABASE_URL=postgresql+psycopg://competitor_intel_app:<PASSWORD>@<POSTGRES_HOST>:5432/competitor_intel
DATABASE_SCHEMA=competitor_intel
```

Never commit `.env`, passwords or API keys.

### Database migration

```bash
alembic upgrade head
```

### Seed reference data

```bash
PYTHONPATH=. python3 scripts/seed_data.py
```

Seed scripts must be idempotent.

### Run one pipeline cycle

```bash
PYTHONPATH=. python3 scripts/run_pipeline.py
```

### Start API and dashboard

```bash
./scripts/start_server.sh
```

The UI must load production data from the API/PostgreSQL. If PostgreSQL is empty, show an explicit empty state rather than synthetic rows.

## Refresh vs Scan vs Discovery

**Refresh** reloads canonical data already stored in PostgreSQL.

**Scan now** starts collection/extraction against active approved source targets.

**Discover sources** looks for new candidate domains/pages/URLs and places them into the source/URL review/assessment workflow. It does not automatically trust or publish discovered sources.

These actions must never be presented as the same operation.

## API Contract

At minimum:

- `GET /api/v1/promotions/top10`
- `GET /api/v1/promotions/{promotion_id}`
- `GET /api/v1/stats/`
- `GET /api/v1/sources/health`
- `GET /health`

Filters should support category, competitor, brand, retailer, promotion mechanic, geography, source, status and validity.

## Testing / Acceptance

Before production readiness, verify:

1. Fresh database migrates successfully.
2. No application query touches `dwh_prod`.
3. Multiple source records can exist in the source registry.
4. A source can be disabled without deleting historical observations.
5. A URL target can be scheduled independently.
6. A successful crawl with zero promotions is recorded as success.
7. A failed crawl is not interpreted as zero promotions.
8. Unchanged content can skip expensive extraction where safe.
9. Changed content produces a new observation.
10. Geography is preserved and normalized.
11. Regional price/promotion observations are not incorrectly merged.
12. Expired promotions do not appear in active Top 10.
13. Promotions older than 90 days do not appear in default Top 10.
14. Promotions without evidence are not presented as verified.
15. Dashboard values exactly match API/PostgreSQL data.
16. Empty/error/stale states are explicit; no fake data exists.
17. Source health exposes crawl failures and stale states.
18. Audit detail can trace a promotion to source evidence.
19. Candidate source discovery does not automatically make a source trusted.
20. Collection does not bypass access controls.

## Production Principles

- Evidence over assumptions.
- PostgreSQL over UI mock data.
- Multiple sources over single-source dependency.
- Source registry over unrestricted repeated web search.
- Source geography over inferred geography.
- Immutable observations over destructive updates.
- Quality gate before ranking.
- Explainable scores over opaque scores.
- Source-specific adapters with tests.
- Least-privilege database access.
- Compliant public collection only.
- Every production behavior change must be represented in documentation and migrations.
