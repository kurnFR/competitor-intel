# TECHNICAL_DESIGN.md — Production Architecture

## 1. Purpose

Implementation contract for the Competitor Promotion Intelligence Platform. The system discovers and monitors approved public sources, stores immutable observations/evidence, validates commercial facts, normalizes geography, resolves entities, deduplicates safely, creates canonical promotions, ranks eligible activities and serves PostgreSQL-backed data to the UI.

Hemat.id is an initial adapter only. The canonical model must support many source classes without redesign.

## 2. Architecture Principles

1. PostgreSQL is the UI source of truth.
2. Use the existing PostgreSQL server but isolated database `competitor_intel` and schema `competitor_intel`.
3. `dwh_prod` is out of scope.
4. Raw observations are immutable.
5. Evidence is mandatory for verified facts.
6. Geography is relational and preserves source wording.
7. Unknown values are never fabricated.
8. Quality gates run before ranking.
9. Material regional/channel differences are never deduplicated away.
10. Money uses PostgreSQL `NUMERIC`.
11. `first_seen_at`, `last_seen_at`, `last_verified_at` are separate.
12. Discovery is separate from approval and crawling.
13. Normal runs crawl approved URL targets; discovery periodically finds candidates.
14. Source-specific collection logic is isolated behind adapters.
15. Public access restrictions are respected; never bypass controls.

## 3. High-Level Architecture

```text
Public Web
  -> Source Discovery
  -> Candidate Sources/URLs
  -> Assessment/Approval
  -> Source + URL Registry
  -> Scheduler
  -> Approved Crawler Targets
  -> Raw Crawl Documents
  -> Change Detection
  -> AI Extraction (changed/relevant content)
  -> Validation
  -> Geography Normalization
  -> Entity Resolution
  -> Promotion Matching/Deduplication
  -> Quality Gate
       |-> PASS -> PostgreSQL -> API -> UI
       |-> REVIEW -> Review Queue
```

A failed crawl is not zero promotions. An unchanged document may skip AI extraction only when the adapter can safely determine that commercial content did not change.

## 4. Source Registry

### `source_registry`

```text
id UUID PK
name TEXT NOT NULL
base_url TEXT NOT NULL
domain TEXT NOT NULL
source_type TEXT NOT NULL
owner_name TEXT NULL
tier INTEGER
reliability_score NUMERIC(5,4)
priority INTEGER
crawl_frequency_minutes INTEGER
adapter_key TEXT
access_status TEXT
is_active BOOLEAN
last_discovery_at TIMESTAMPTZ
last_crawled_at TIMESTAMPTZ
last_success_at TIMESTAMPTZ
last_error_at TIMESTAMPTZ
created_at TIMESTAMPTZ
updated_at TIMESTAMPTZ
```

### `source_urls`

```text
id UUID PK
source_id UUID FK
url TEXT NOT NULL
canonical_url TEXT NULL
page_type TEXT
category_hint TEXT
crawl_priority INTEGER
crawl_frequency_minutes INTEGER NULL
is_active BOOLEAN
last_crawled_at TIMESTAMPTZ
last_success_at TIMESTAMPTZ
last_http_status INTEGER
last_content_hash TEXT
failure_count INTEGER
next_crawl_at TIMESTAMPTZ
created_at TIMESTAMPTZ
updated_at TIMESTAMPTZ
```

The URL registry is the primary target list for normal scheduled runs.

## 5. Source Discovery

Discovery is a separate scheduled process using permitted search engines, sitemaps, feeds, category pages, site navigation and public URL patterns.

Discovery results enter a candidate queue. They do not automatically become active sources.

Assessment checks relevance, public accessibility, source type, adapter feasibility and initial reliability.

Supported source classes include official manufacturer/brand sites, retailer/modern trade, convenience retail, local/regional retail, verified marketplace stores, public e-commerce, promotion aggregators, established media and permitted public social/content sources.

Examples such as Superindo, Alfamart, Indomaret, Hypermart, Tokopedia, Shopee and TikTok Shop are candidate sources only; each must be assessed for public access, terms and technical feasibility.

## 6. Crawl Scheduling

Normal scheduled cycle:

1. load active approved sources
2. load due active URLs
3. prioritize by source priority, historical yield, freshness, validity and failures
4. fetch
5. persist crawl job/document
6. compare content hash/change signal
7. extract changed/relevant content
8. validate and persist observation
9. update source health

Starting frequencies are configurable; high-value promotion pages may be 15–60 minutes, retailer promotion pages 1–6 hours, stable catalogs 6–24 hours, and source discovery daily/weekly.

Use bounded retry/backoff.

## 7. Runtime Stack

| Concern | Technology |
|---|---|
| Language | Python 3.12+ |
| API | FastAPI |
| Validation | Pydantic |
| ORM | SQLAlchemy 2 |
| Driver | psycopg3 |
| HTTP | httpx |
| HTML | BeautifulSoup/selectolax |
| Main content | trafilatura |
| Browser | Playwright when required |
| PDF | PyMuPDF |
| OCR | Tesseract/approved equivalent |
| AI | structured-output LLM gateway |
| Database | existing PostgreSQL / `competitor_intel` |
| Similarity | pg_trgm; pgvector optional |
| Scheduler | APScheduler for MVP |
| Queue/cache | optional Redis when workload requires it |

## 8. Database Boundary

```text
Existing PostgreSQL Server
├── dwh_prod                 <- forbidden
└── competitor_intel         <- application database
    └── competitor_intel     <- application schema
```

No cross-database foreign keys.

```sql
CREATE DATABASE competitor_intel;
CREATE ROLE competitor_intel_app LOGIN PASSWORD '<STRONG_PASSWORD>';
GRANT CONNECT ON DATABASE competitor_intel TO competitor_intel_app;
```

Inside the application database:

```sql
CREATE SCHEMA competitor_intel AUTHORIZATION competitor_intel_app;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

## 9. Configuration

```env
DATABASE_URL=postgresql+psycopg://competitor_intel_app:<PASSWORD>@<HOST>:5432/competitor_intel
DATABASE_SCHEMA=competitor_intel
LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=
CRAWL_INTERVAL_MINUTES=30
TOP10_MAX_AGE_DAYS=90
OPEN_ENDED_PROMOTION_MAX_VERIFICATION_DAYS=7
```

Source-specific configuration belongs in the registry/configuration layer, not scattered constants.

## 10. Migrations

Use Alembic and build the schema from an empty `competitor_intel` database.

```bash
alembic upgrade head
```

Every schema change requires migration, model/schema updates and tests.

## 11. Data Layers

```text
SOURCE CONTROL
  source_registry
  source_urls
  crawl_jobs
  crawl_documents

OBSERVATION
  extraction_runs
  promotion_observations

MASTER DATA
  competitors
  brands
  products
  retailers
  geography_reference

CANONICAL
  promotions
  promotion_geographies
  promotion_conditions

PROVENANCE
  promotion_evidence

QUALITY
  validation_results
  entity_mapping
  review_queue
```

## 12. Crawl Jobs and Documents

Record every attempt with source, URL, status, timestamps, HTTP status, error and retry information. A successful crawl with zero extracted promotions remains `SUCCESS`.

Documents retain URL, content type, text/raw-content reference, SHA-256 content hash, retrieval timestamp and metadata.

## 13. AI Extraction

Each extraction stores model, prompt version, schema version, timestamps, status and raw structured response.

Extraction fields include product, brand, competitor, SKU/pack size, price, mechanic, retailer, channel, source geography text, normalized geography suggestions, validity, conditions, evidence references and field confidence.

AI must not invent missing values.

## 14. Immutable Observations

`promotion_observations` records what a source showed at a point in time. Never overwrite historical observations. Canonical promotions are derived from observations.

## 15. Geography

Use `geography_reference` plus `promotion_geographies` with `scope_type`, `scope_name`, `scope_role` (`INCLUDE`/`EXCLUDE`), `source_text` and confidence.

Preserve exact source wording. Never default missing geography to Indonesia. Never silently expand `Jawa` or `Jabodetabek` into administrative units without an approved mapping.

## 16. Canonical Promotions

Use `NUMERIC(18,2)` for monetary values.

Material identity dimensions:

```text
product
retailer
channel
promotion mechanic
mechanic parameters
price
validity
geographic scope
conditions
```

Regional/channel/price differences that materially change applicability must remain distinct.

## 17. Evidence

Every verified promotion links to source documents and evidence. Evidence should support price, mechanic, validity and geography separately where practical.

## 18. Validation

Deterministic validation follows AI extraction.

Price: non-negative; discount arithmetic checked; currency known.

Dates: end >= start; explicit expiry controls active status; local timezone respected.

Geography: source wording preserved; mapping controlled or UNKNOWN; material ambiguity -> review.

Identity: exact/alias/SKU before fuzzy matching; weak match -> review.

## 19. Entity Resolution

Resolution order:

1. stable source identifier
2. exact normalized combination
3. SKU
4. approved alias
5. pg_trgm similarity
6. review queue

Store method and similarity/approval information.

## 20. Deduplication

Match using product, retailer, channel, mechanic, parameters, price, validity, geography and conditions.

Multiple sources may support one canonical promotion. Material regional/channel/price differences must not be merged.

## 21. Quality Gate and Ranking

Only quality-approved records enter ranking.

```text
current validity
AND last_verified_at >= now - 90 days
AND evidence exists
AND target category
AND source approved
AND identity sufficiently resolved
AND geography sufficiently understood
AND no material unresolved contradiction
AND status != REJECTED
```

Ranking factors are configurable and explainable. UI label: `Impact Score`.

## 22. Status

```text
UPCOMING
ACTIVE
EXPIRED
UNKNOWN
REVIEW_REQUIRED
REJECTED
```

An explicit expired end date always wins over recent crawl freshness.

## 23. API/UI Boundary

```text
Crawler -> PostgreSQL -> FastAPI -> UI
```

The UI must never contain production mock rows or fallback generated promotions.

Minimum endpoints:

```text
GET /health
GET /api/v1/promotions/top10
GET /api/v1/promotions/{promotion_id}
GET /api/v1/stats/
GET /api/v1/sources/health
```

Filters support category, competitor, brand, retailer, mechanic, geography, source, status and validity.

## 24. Observability

Track source discovery count, active sources, crawl success/failure/block rate, content-change rate, extraction success, evidence coverage, geography resolution, entity resolution, review rate, duplicate/conflict rate and last successful crawl.

## 25. Testing

Required tests include source discovery approval, successful zero-result crawl, failed crawl semantics, safe change detection, geography inclusion/exclusion, regional non-merge, expiry, 90-day freshness, evidence requirement, API/PostgreSQL consistency and prohibition of `dwh_prod` access.

Every source adapter needs representative fixtures and regression tests.

## 26. Compliance and Security

Collect only permitted public information. Do not bypass access controls. Do not store secrets in Git. Use least-privilege database roles. Do not expose credentials or internal stack traces.

## 27. Implementation Order

```text
source registry + URL registry
  -> geography migrations
  -> crawl/document persistence
  -> Hemat.id reference adapter
  -> source discovery workflow
  -> structured extraction
  -> validation/evidence
  -> entity resolution/deduplication
  -> quality gate/ranking
  -> API
  -> PostgreSQL-backed UI
  -> additional approved source adapters
  -> regional analytics
```

Do not prioritize UI polish over a proven real-data vertical slice.
