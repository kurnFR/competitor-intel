# FMCG Competitor Promotion Intelligence Platform

AI-powered competitive promotion intelligence for the Indonesian FMCG snack market, initially focused on biscuits, crackers, cookies and wafers.

> **Documentation freeze:** These documents define the requirements that implementation must follow. Do not add mock promotion data or silently invent missing commercial facts.

## Source of Truth

The **PostgreSQL database is the source of truth for the UI**. The dashboard must query the API, and the API must query PostgreSQL. The UI must never use hard-coded promotion rows, demo JSON, or generated fallback records.

The application may reuse the customer's **existing PostgreSQL server**, but the application database must be isolated from unrelated DWH data. The current target database is:

```text
competitor_intel
```

with application schema:

```text
competitor_intel
```

The application must not read or modify `dwh_prod` unless a future approved integration explicitly changes this requirement.

## What the system answers

The primary business question is:

> What are the 10 most commercially important competitor promotions that are currently active, recently verified, and supported by reliable source evidence?

Every displayed promotion must be traceable to:

- source URL and domain
- crawl/retrieval timestamp
- source evidence
- extracted fields
- geographic scope
- retailer/channel scope
- validity period
- validation result
- AI confidence
- canonical product/brand/competitor mapping

## Initial Source Strategy

The first production source is **Hemat.id**. Do not confuse it with `hemat.co.id`.

Hemat.id is treated as a secondary promotion/price intelligence source and must preserve the exact geographic wording published by the source. Source reliability is configurable in `source_registry`; it must not be hard-coded into ranking logic.

Additional official retailer, brand, marketplace and other reliable sources may be added later through the source registry and source-specific adapters.

## Critical Business Rules

### 1. Geography is first-class data

A promotion is not fully identified by product + retailer + price. Geographic scope can change the commercial meaning of the promotion.

The system must preserve both:

- `source_geography_text`: exact wording from the source
- normalized geographic scopes: structured inclusion/exclusion records

Examples:

```text
Berlaku di Jawa
Berlaku di Jawa, Bali, Lombok, kecuali Indomaret Point
Berlaku di Jabodetabek, Palembang
```

Never default an unknown geography to `Indonesia`. `Indonesia` may only be assigned when the source explicitly states national scope or an approved business rule establishes it.

### 2. Regional prices are separate observations

The same SKU can have different promotion prices in Java, Sumatera, Kalimantan, Sulawesi, Bali, etc. Different geographic observations must not be merged into one promotion merely because product and retailer match.

### 3. Evidence before trust

No evidence = not verified.

The system must not fabricate a manufacturer, competitor, price, date, promotion mechanic or geography. Unknown values remain `NULL`/`UNKNOWN` and may enter the review queue.

### 4. Active is not the same as recently crawled

Track separately:

- `first_seen_at`
- `last_seen_at`
- `last_verified_at`

The UI must show actual data freshness.

### 5. Top 10 eligibility

Default Top 10 candidates must:

- belong to the target categories
- be currently valid
- satisfy the 90-day freshness rule
- have usable evidence
- pass mandatory validation
- not be rejected
- not contain unresolved critical contradictions

Ranking occurs **after** the quality gate.

## Architecture

```text
Public Sources
     |
     v
Source Registry / Scheduler
     |
     v
Crawler / Browser / Parser
     |
     v
Raw Crawl Documents + Content Hash
     |
     v
AI Structured Extraction
     |
     v
Field Validation + Geography Normalization
     |
     v
Entity Resolution
     |
     v
Promotion Matching / Deduplication
     |
     v
Quality Gate
     |-------------------> Review Queue
     v
Canonical PostgreSQL Data
     |
     v
FastAPI
     |
     +---- Overview
     +---- Promotions
     +---- Regional Pricing
     +---- Competitors
     +---- Sources
     +---- Review Queue
     +---- Settings
```

## PostgreSQL Data Model

The principal layers are:

1. **Source layer** — source registry, crawl jobs, crawl documents
2. **Observation layer** — immutable AI extraction observations
3. **Canonical layer** — competitors, brands, products, retailers, promotions
4. **Geography layer** — promotion geographic inclusions/exclusions
5. **Evidence layer** — field-level or passage-level evidence
6. **Quality layer** — validation, confidence, review queue
7. **Analytics layer** — Top 10 and regional price/activity views

See [`DATA_MODEL.md`](DATA_MODEL.md).

## UI / UX

The dashboard is an enterprise intelligence application, not a static report. The recommended navigation is:

```text
Overview
Promotions
Regional Pricing
Competitors
Sources
Review Queue
Settings
```

The main promotion workflow uses a filterable table plus a right-side detail drawer. The drawer exposes price, mechanic, retailer, geography, validity, evidence, source, verification timestamp and field-level confidence without forcing the user to leave the list.

See [`UI_UX_DESIGN.md`](UI_UX_DESIGN.md).

## Documentation Set

| Document | Purpose |
|---|---|
| `README.md` | Project overview, setup and operating principles |
| `FMCG Competitor Promotion.md` | Product requirements / PRD |
| `TECHNICAL_DESIGN.md` | Technical architecture and implementation requirements |
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

Copy `.env.example` to `.env` and configure the **competitor_intel** database only.

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

### Run one pipeline cycle

```bash
PYTHONPATH=. python3 scripts/run_pipeline.py
```

### Start API and dashboard

```bash
./scripts/start_server.sh
```

The UI must load promotion data from the API/PostgreSQL. If PostgreSQL is empty, the UI should show an explicit empty state rather than synthetic rows.

## Refresh vs Scan

**Refresh** means reload the latest data already stored in PostgreSQL.

**Scan now** means start a new collection/extraction pipeline against configured sources.

These actions must never be presented as the same operation.

## API Contract

The API should provide at minimum:

- `GET /api/v1/promotions/top10`
- `GET /api/v1/promotions/{promotion_id}`
- `GET /api/v1/stats/`
- `GET /api/v1/sources/health`
- `GET /health`

Filters should support category, competitor, brand, retailer, promotion mechanic, geography, status and validity.

## Testing / Acceptance

Before calling the system production-ready, verify at minimum:

1. A fresh database can be migrated with `alembic upgrade head`.
2. No application query touches `dwh_prod`.
3. A real Hemat.id crawl creates a raw document and an observation.
4. A real promotion reaches PostgreSQL only after validation.
5. Geography from the source is preserved and normalized.
6. Two identical promotions are deduplicated.
7. Two regional price/promotion observations are not incorrectly merged.
8. Expired promotions disappear from the default Top 10.
9. Promotions without usable evidence do not appear as verified.
10. The dashboard displays exactly what the API returns from PostgreSQL.
11. Empty/error/stale states are explicit; no fake data is displayed.
12. The audit drawer can trace every displayed promotion to source evidence.

## Production Principles

- Evidence over assumptions.
- PostgreSQL over UI mock data.
- Source geography over inferred geography.
- Immutable observations over destructive updates.
- Quality gate before ranking.
- Explainable scores over opaque scores.
- Least-privilege database access.
- Source-specific parsers with tests.
- Every production change must be represented in the documentation and migrations.
