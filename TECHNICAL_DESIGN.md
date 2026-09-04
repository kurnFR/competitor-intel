# TECHNICAL_DESIGN.md — Production Architecture

## 1. Purpose

This document is the implementation contract for the Competitor Promotion Intelligence Platform.

The system collects public promotion intelligence, stores immutable observations and source evidence, validates and normalizes commercial facts, resolves entities, deduplicates observations without losing material regional differences, creates canonical promotions, ranks eligible activities, and serves PostgreSQL-backed data to the dashboard.

The primary production source for the MVP is **Hemat.id**. Source-specific behavior must be isolated behind adapters.

## 2. Architecture Principles

1. PostgreSQL is the canonical source of truth for the UI.
2. Raw observations are immutable.
3. Evidence is mandatory for verified commercial facts.
4. Geography is a first-class relational dimension.
5. Source geography must be preserved verbatim.
6. Unknown values are never fabricated.
7. Quality gates run before ranking.
8. Regional differences must not be deduplicated away.
9. Monetary values use PostgreSQL `NUMERIC`, not floating point.
10. `last_seen_at` and `last_verified_at` are separate concepts.
11. The application may use the existing PostgreSQL server but must remain isolated from `dwh_prod`.
12. Source adapters must be testable with fixtures.

## 3. Database Boundary

The application uses the existing PostgreSQL server and the dedicated database:

```text
competitor_intel
```

with schema:

```text
competitor_intel
```

The application must not connect to, query, migrate, or modify `dwh_prod`.

Recommended topology:

```text
Existing PostgreSQL Server
├── dwh_prod                 <- out of scope
└── competitor_intel         <- application database
    └── competitor_intel     <- application schema
```

No cross-database foreign keys are allowed.

## 4. High-Level Data Flow

```text
Source Registry
      |
      v
Scheduler / Discovery
      |
      v
Source Adapter
      |
      v
HTTP / Browser Fetch
      |
      v
Raw Crawl Document
      |
      v
Text / OCR / Structured Content
      |
      v
AI Extraction
      |
      v
Field Validation
      |
      v
Geography Normalization
      |
      v
Entity Resolution
      |
      v
Promotion Matching
      |
      +-------- existing commercial event --------+
      |                                             |
      v                                             v
Update canonical promotion                Create canonical promotion
      |                                             |
      +-------------------+-------------------------+
                          v
                     Quality Gate
                     /          \
                    /            \
                 PASS            REVIEW
                  |                |
                  v                v
               Ranking       Review Queue
                  |
                  v
             PostgreSQL
                  |
                  v
                API
                  |
                  v
                 UI
```

## 5. Runtime Components

```text
app/
├── api
├── core
├── db
├── models
├── schemas
├── services
│   ├── crawling
│   ├── extraction
│   ├── validation
│   ├── geography
│   ├── entity_resolution
│   ├── deduplication
│   ├── ranking
│   └── review
└── web
```

Recommended stack:

| Concern | Technology |
|---|---|
| Language | Python 3.12+ |
| API | FastAPI |
| Validation | Pydantic |
| ORM | SQLAlchemy 2 |
| Driver | psycopg3 |
| HTTP | httpx |
| HTML | BeautifulSoup / selectolax |
| Content extraction | trafilatura |
| Browser | Playwright when required |
| PDF | PyMuPDF |
| OCR | Tesseract or approved equivalent |
| AI | Structured-output LLM gateway |
| Database | Existing PostgreSQL server / `competitor_intel` DB |
| Similarity | pg_trgm; pgvector optional |
| Scheduler | APScheduler for MVP; queue worker later if needed |
| Cache/queue | Redis optional |
| Object storage | S3-compatible or local persistent storage |

Do not introduce infrastructure merely for architectural fashion. Add Redis/Celery/object storage only when the actual workload requires it.

## 6. PostgreSQL Provisioning

Create the database once on the existing PostgreSQL server:

```sql
CREATE DATABASE competitor_intel;
```

Create a dedicated application role:

```sql
CREATE ROLE competitor_intel_app LOGIN PASSWORD '<STRONG_PASSWORD>';
GRANT CONNECT ON DATABASE competitor_intel TO competitor_intel_app;
```

Inside the database:

```sql
CREATE SCHEMA competitor_intel AUTHORIZATION competitor_intel_app;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

Do not put passwords in Git.

The runtime role should receive only the permissions required by the application. Migration ownership and application runtime permissions may be separated in production.

## 7. Configuration

```env
DATABASE_URL=postgresql+psycopg://competitor_intel_app:<PASSWORD>@<HOST>:5432/competitor_intel
DATABASE_SCHEMA=competitor_intel
```

Other configuration must include:

```env
LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=
CRAWL_INTERVAL_MINUTES=30
HTTP_TIMEOUT_SECONDS=30
TOP10_MAX_AGE_DAYS=90
```

The application must fail clearly at startup when required configuration is missing.

## 8. Migration Rules

Use Alembic.

```bash
alembic upgrade head
```

The schema must be buildable from an empty `competitor_intel` database. No migration may depend on existing DWH tables.

Every schema change must have:

- an Alembic migration
- corresponding model/schema updates
- tests for important integrity constraints
- documentation update when business behavior changes

## 9. Canonical Data Model

The production model has seven layers:

```text
SOURCE
  source_registry
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

CANONICAL COMMERCIAL DATA
  promotions
  promotion_geographies
  promotion_conditions

PROVENANCE
  promotion_evidence
  observation_links

QUALITY
  validation_results
  review_queue

ANALYTICS
  ranking snapshots/views as required
```

## 10. Source Registry

Suggested fields:

```text
id UUID PK
name TEXT NOT NULL
base_url TEXT NOT NULL
domain TEXT NOT NULL
source_type ENUM/TEXT
tier INTEGER
reliability_score NUMERIC(5,4)
country_code TEXT
language_code TEXT
is_active BOOLEAN
crawl_frequency_minutes INTEGER
priority INTEGER
robots_allowed BOOLEAN
last_crawled_at TIMESTAMPTZ
last_success_at TIMESTAMPTZ
last_error_at TIMESTAMPTZ
created_at TIMESTAMPTZ
updated_at TIMESTAMPTZ
```

MVP source:

```text
Hemat.id
```

The source adapter should not hard-code reliability into business ranking. The registry owns the configurable value.

## 11. Crawl Jobs

Track every crawl attempt:

```text
id UUID PK
source_id UUID FK
url TEXT
job_type TEXT
status TEXT
started_at TIMESTAMPTZ
completed_at TIMESTAMPTZ
http_status INTEGER
error_code TEXT
error_message TEXT
retry_count INTEGER
content_hash TEXT
created_at TIMESTAMPTZ
```

Statuses:

```text
QUEUED
RUNNING
SUCCESS
FAILED
BLOCKED
SKIPPED
```

Retries must use bounded backoff. Repeated source failures must not cause infinite loops.

## 12. Crawl Documents

Store a durable representation of each retrieved source document:

```text
id UUID PK
crawl_job_id UUID FK
source_id UUID FK
url TEXT NOT NULL
canonical_url TEXT
content_type TEXT
title TEXT
raw_content_uri TEXT
text_content TEXT
content_hash TEXT
published_at TIMESTAMPTZ
retrieved_at TIMESTAMPTZ
language_code TEXT
http_status INTEGER
metadata JSONB
created_at TIMESTAMPTZ
```

Use SHA-256 for content hashing.

For large PDF/image/html payloads, store the payload in durable object storage and retain URI + metadata in PostgreSQL. The MVP may retain extracted text directly in PostgreSQL.

## 13. Extraction Runs

Every AI extraction request should be identifiable:

```text
id UUID PK
document_id UUID FK
model_name TEXT
prompt_version TEXT
schema_version TEXT
started_at TIMESTAMPTZ
completed_at TIMESTAMPTZ
status TEXT
raw_response JSONB
error_message TEXT
created_at TIMESTAMPTZ
```

This makes model/prompt changes auditable.

## 14. Promotion Observations

This is the immutable observation layer.

Suggested fields:

```text
id UUID PK
document_id UUID FK
extraction_run_id UUID FK
source_promotion_key TEXT
raw_extracted JSONB
normalized_extracted JSONB
observed_at TIMESTAMPTZ
created_at TIMESTAMPTZ
```

An observation answers:

> What did the system believe the source said at this point in time?

Do not overwrite historical observations merely because the same promotion is seen again.

## 15. Master Data

### Competitors

```text
id
name
normalized_name
status
created_at
updated_at
```

### Brands

```text
id
competitor_id
name
normalized_name
status
created_at
updated_at
```

### Products

```text
id
brand_id
name
normalized_name
variant
pack_size_value
pack_size_unit
sku
category
status
created_at
updated_at
```

### Retailers

```text
id
name
normalized_name
retailer_type
status
created_at
updated_at
```

Unknown manufacturer/competitor must remain `NULL` or `UNKNOWN`; never use placeholder values such as `FMCG Manufacturer`.

## 16. Geography Model

Do not use one `promotions.geography TEXT` column as the canonical geography model.

### geography_reference

Suggested fields:

```text
id UUID PK
parent_id UUID NULL FK
scope_type TEXT
name TEXT
normalized_name TEXT
country_code TEXT
is_active BOOLEAN
mapping_version TEXT
created_at TIMESTAMPTZ
updated_at TIMESTAMPTZ
```

Scope types:

```text
NATIONAL
ISLAND_GROUP
REGION
PROVINCE
METRO
CITY
DISTRICT
STORE
STORE_GROUP
ONLINE
OTHER
UNKNOWN
```

### promotion_geographies

```text
id UUID PK
promotion_id UUID FK
geography_id UUID NULL FK
scope_type TEXT NOT NULL
scope_name TEXT NOT NULL
source_text TEXT NOT NULL
scope_role TEXT NOT NULL   -- INCLUDE / EXCLUDE
confidence NUMERIC(5,4)
created_at TIMESTAMPTZ
```

A promotion can have many included and excluded scopes.

Example:

```text
Promotion 123
INCLUDE Jawa
INCLUDE Bali
INCLUDE Lombok
EXCLUDE Indomaret Point
```

The exact source sentence remains in `source_text`.

## 17. Geography Normalization Rules

1. Preserve source wording exactly.
2. Normalize only through deterministic mappings or validated AI suggestions.
3. Never turn missing geography into `Indonesia` automatically.
4. Do not expand `Jawa` into provinces unless a mapping is explicitly configured.
5. Keep commercial regions such as `Jabodetabek` as valid scopes.
6. Keep retailer/store exclusions separate from geographic inclusion.
7. If geography is ambiguous and materially affects applicability, set `REVIEW_REQUIRED`.

## 18. Canonical Promotions

Use `NUMERIC(18,2)` for monetary values.

Suggested fields:

```text
id UUID PK
competitor_id UUID NULL FK
brand_id UUID NULL FK
product_id UUID NULL FK
retailer_id UUID NULL FK

product_name TEXT
sku TEXT
pack_size_value NUMERIC(12,3)
pack_size_unit TEXT
category TEXT

regular_price NUMERIC(18,2)
promo_price NUMERIC(18,2)
currency CHAR(3)

discount_percentage_stated NUMERIC(7,3)
discount_percentage_calculated NUMERIC(7,3)

promotion_type TEXT
buy_quantity INTEGER
free_quantity INTEGER
bundle_quantity INTEGER
cashback_amount NUMERIC(18,2)
voucher_amount NUMERIC(18,2)
minimum_purchase_amount NUMERIC(18,2)
minimum_purchase_quantity INTEGER
maximum_quantity INTEGER
gift_description TEXT
promotion_title TEXT
promotion_description TEXT

start_date TIMESTAMPTZ NULL
end_date TIMESTAMPTZ NULL
channel TEXT

source_geography_text TEXT NULL

status TEXT

source_reliability NUMERIC(5,4)
ai_confidence NUMERIC(5,4)

first_seen_at TIMESTAMPTZ
last_seen_at TIMESTAMPTZ
last_verified_at TIMESTAMPTZ

rank_score NUMERIC(8,3)
created_at TIMESTAMPTZ
updated_at TIMESTAMPTZ
```

`source_geography_text` is retained for convenient display, while `promotion_geographies` is authoritative for normalized scope.

## 19. Promotion Conditions

Do not overload the promotion table with every possible condition. Use a child table where conditions are variable.

```text
promotion_conditions
---------------------
id
promotion_id
condition_type
condition_value_text
condition_value_numeric
source_text
created_at
```

Examples:

```text
MEMBER_ONLY
PAYMENT_METHOD
APP_ONLY
MINIMUM_PURCHASE
MAXIMUM_QUANTITY
STORE_EXCLUSION
GEOGRAPHY_EXCLUSION
VOUCHER_CODE
OTHER
```

## 20. Evidence

Every canonical promotion must link to one or more evidence records.

```text
promotion_evidence
------------------
id UUID PK
promotion_id UUID FK
document_id UUID FK
field_name TEXT
 evidence_text TEXT
source_url TEXT
page_number INTEGER NULL
locator JSONB NULL
confidence NUMERIC(5,4)
created_at TIMESTAMPTZ
```

There must be no verified promotion without source evidence.

Evidence should be granular enough to support price, mechanic, validity and geography separately where possible.

## 21. Validation

Validation is deterministic after AI extraction.

### Price

- price must be non-negative
- promo price should not exceed regular price for ordinary discount mechanics unless evidence explains the exception
- currency must be known or explicitly defaulted to IDR by an approved source rule
- stated and calculated discount differences must be flagged when materially inconsistent

### Dates

- end date must not precede start date
- dates must be interpreted in Indonesia/local source context where known
- an expired promotion cannot be active
- missing end date requires recent verification

### Geography

- source text must exist when geography is claimed
- normalized scope must map to a controlled reference or remain `UNKNOWN`
- material ambiguity enters review

### Identity

- brand/product matching uses exact normalized match first, then controlled fuzzy matching
- unresolved identity is not silently assigned to a competitor

## 22. Status Lifecycle

Allowed canonical statuses:

```text
UPCOMING
ACTIVE
EXPIRED
UNKNOWN
REVIEW_REQUIRED
REJECTED
```

Recommended active rule:

```text
start_date <= now
AND (end_date >= now OR end_date IS NULL)
AND last_verified_at satisfies the no-end-date freshness rule when end_date is NULL
AND quality gate = PASS
```

A promotion with an explicit expired end date is `EXPIRED`, even if it was crawled recently.

## 23. Freshness

The default Top 10 freshness limit is 90 days.

Use:

```sql
last_verified_at >= NOW() - INTERVAL '90 days'
```

for trust/freshness gating.

Do not use a 90-day observation to imply that the promotion is still active. Current validity must also be satisfied.

For promotions without explicit end dates, use a much stricter configured verification window, recommended at 7 days for MVP.

## 24. Entity Resolution

Resolution order:

1. exact stable source identifier when available
2. exact normalized brand/product/retailer combination
3. SKU match
4. approved alias mapping
5. pg_trgm similarity
6. review queue

Never resolve solely from a weak product-name similarity when the commercial impact could change.

Store resolution decisions in `entity_mapping`:

```text
id
entity_type
source_value
canonical_id
match_method
similarity_score
approved_by
created_at
```

## 25. Deduplication and Promotion Matching

The system must distinguish:

- duplicate observations of the same commercial activity
- materially different regional/channel/store activities

A candidate match should consider:

```text
product_id / resolved product
retailer_id
channel
promotion_type
mechanic parameters
price
validity
geographic inclusion
geographic exclusion
```

If geography, price, validity or conditions differ materially, keep separate canonical promotions or separate promotion observations as appropriate.

Do not deduplicate merely on product name + retailer.

## 26. Ranking

Ranking is performed only after the quality gate.

Suggested normalized factors:

```text
promotion_strength
source_reliability
freshness
category_relevance
ai_confidence
evidence_quality
commercial_impact
```

Example configurable formula:

```text
rank_score =
    0.30 * promotion_strength
  + 0.20 * source_reliability
  + 0.15 * freshness
  + 0.15 * category_relevance
  + 0.10 * ai_confidence
  + 0.10 * evidence_quality
```

The exact weights must be configuration, not hidden code constants.

The UI label should be `Impact Score`, not `Accuracy`.

Ranking must be deterministic for equal input data.

## 27. Top 10 Query Contract

Default eligibility:

```text
status = ACTIVE
quality gate = PASS
last_verified_at >= now - 90 days
category in configured target categories
evidence_count > 0
```

Then:

```text
ORDER BY rank_score DESC, last_verified_at DESC, id
LIMIT 10
```

User filters may narrow the result. A historical explorer may use a different date range but must not label historical records as current Top 10.

## 28. API Requirements

At minimum:

```text
GET /api/v1/promotions/top10
GET /api/v1/promotions/{id}
GET /api/v1/promotions
GET /api/v1/stats/
GET /api/v1/sources/health
GET /health
```

Top 10 response should include:

```json
{
  "promotion_id": "...",
  "competitor": "Mayora",
  "brand": "Roma",
  "product": "Roma Sari Gandum Sandwich",
  "category": "BISCUIT",
  "regular_price": 11990,
  "promo_price": 7900,
  "discount_percentage": 34.0,
  "promotion_type": "DISCOUNT",
  "retailer": "Hypermart",
  "channel": "OFFLINE_RETAIL",
  "geography": {
    "source_text": "Berlaku di Jawa",
    "includes": ["Jawa"],
    "excludes": []
  },
  "valid_from": "...",
  "valid_until": "...",
  "last_verified_at": "...",
  "impact_score": 89.0,
  "confidence": {
    "product": 0.98,
    "price": 0.99,
    "promotion": 0.97,
    "geography": 0.96,
    "validity": 0.95
  }
}
```

The API must return an explicit data freshness timestamp.

## 29. UI Data Contract

The dashboard reads only through the API.

```text
PostgreSQL
   -> SQLAlchemy/service
   -> FastAPI
   -> frontend
```

No production promotion constants are permitted in frontend code.

If PostgreSQL has no rows, render an empty state.

If PostgreSQL is unavailable, render a database error state.

If source data is stale, render a stale-data warning.

## 30. Source Adapter Design

Each source should implement a predictable adapter contract:

```text
SourceAdapter
├── discover()
├── fetch(url)
├── parse_documents()
├── extract_candidates()
├── extract_source_metadata()
└── health_check()
```

Hemat.id should have fixture tests covering:

- normal promotion page
- missing price
- percentage discount
- Buy X Get Y
- missing dates
- explicit geographic scope
- multiple geographic scopes
- geographic exclusions
- retailer/store exclusions
- changed HTML structure
- blocked/timeout response

## 31. Scheduler

MVP may use APScheduler.

Recommended baseline:

- Hemat.id: 30–60 minutes for priority pages
- source-specific schedules configurable in `source_registry`
- retries with exponential backoff
- no overlapping runs for the same source unless explicitly allowed

Near-expiry promotions may be rechecked more frequently.

Scheduler times must be stored in UTC and displayed in the user's configured/local timezone.

## 32. Source Health

Expose:

```text
source
last_success_at
last_error_at
last_http_status
success_rate
consecutive_failures
last_document_count
last_promotion_count
```

A crawler failure must not be interpreted as zero promotions.

## 33. Review Queue

Create review items for:

- low confidence
- unknown competitor
- ambiguous product
- price conflict
- date conflict
- geography ambiguity
- source parsing failure
- suspected material duplicate
- unsupported promotion mechanic

The UI must allow a reviewer to see source evidence before approving.

## 34. Security

- secrets only in environment/secret manager
- least-privilege DB roles
- no credentials in logs
- sanitize user-supplied URLs
- respect robots.txt and source terms/limits
- do not bypass authentication or anti-bot controls
- audit administrative changes

## 35. Observability

Log structured events for:

```text
crawl_started
crawl_completed
crawl_failed
extraction_started
extraction_failed
validation_failed
entity_resolved
promotion_created
promotion_updated
promotion_rejected
review_created
```

Each event should carry source/job/document/promotion identifiers when available.

## 36. Testing Strategy

### Unit tests

- price calculations
- promotion taxonomy normalization
- geography parsing
- validity rules
- ranking
- deduplication

### Fixture tests

- Hemat.id HTML/page examples
- OCR examples where required

### Integration tests

- empty database migration
- ingestion into PostgreSQL
- API reads canonical data
- geography joins
- evidence retrieval

### End-to-end acceptance test

```text
Hemat.id fixture/live page
 -> crawl document
 -> AI extraction fixture
 -> validation
 -> geography normalization
 -> entity resolution
 -> deduplication
 -> canonical promotion
 -> PostgreSQL
 -> API
 -> Top 10 response
 -> UI detail drawer
```

## 37. Operational Invariants

The implementation is considered broken if any of these occur:

- UI shows a promotion that is not present in PostgreSQL
- promotion appears verified without evidence
- unknown geography becomes Indonesia automatically
- regional promotions are merged incorrectly
- expired promotion appears in default Top 10
- source failure is shown as zero activity
- monetary values use floating-point storage
- application accesses `dwh_prod`
- production UI falls back to demo data
- a model response can bypass deterministic validation

## 38. Definition of Done

Before further feature expansion:

1. Documentation matches code behavior.
2. Database migrations build from empty `competitor_intel`.
3. Real Hemat.id ingestion is reproducible.
4. Geography is stored relationally.
5. Source evidence is auditable.
6. PostgreSQL is the UI source of truth.
7. Top 10 passes all quality gates.
8. Source health is observable.
9. Tests cover regional deduplication and stale/expired records.
10. No mock production data remains in the dashboard.
