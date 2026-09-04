# IMPLEMENTATION_ALIGNMENT.md

# Competitor Promotion Intelligence — Requirements / Implementation Alignment

**Repository:** `kurnFR/competitor-intel`  
**Authoritative branch:** `master`  
**Status:** Architecture checkpoint and implementation alignment baseline  
**Date:** 2026-09-05

---

## 1. Purpose

This document closes the gap between the product requirements, technical design, and the implementation currently present in `master`.

It is intentionally implementation-aware. It records:

- requirements already represented by the repository
- implementation that should be kept
- implementation that must be changed
- known bugs / correctness risks
- components that need to be rewritten
- missing components that must be added
- functionality that must not be introduced
- PostgreSQL migration requirements
- acceptance criteria for implementation completion

This document must be treated together with:

- `FMCG Competitor Promotion.md` — product requirements
- `TECHNICAL_DESIGN.md` — technical architecture
- source code under `app/`
- Alembic migrations

The goal is that **requirements, architecture, and implementation remain synchronized**.

---

# 2. Current Architecture Assessment

The existing implementation is a valid MVP foundation. It already contains the major concepts required by the architecture:

```text
Source
  -> Crawl Job
  -> Crawl Document
  -> Promotion Observation
  -> AI Extraction
  -> Validation
  -> Entity Resolution
  -> Deduplication
  -> Canonical Promotion
  -> Evidence
  -> Ranking
  -> API
```

The implementation should **not be discarded and rebuilt from zero**.

However, several components are currently simplified MVP implementations and are not yet strong enough for reliable continuous competitor intelligence.

The main correctness risks are:

1. weak promotion identity / deduplication
2. overly permissive entity resolution
3. insufficient distinction between observed data and canonical data
4. insufficient promotion lifecycle handling
5. weak handling of missing or uncertain dates
6. fragile LLM JSON extraction
7. crawler limitations for dynamic/PDF/image content
8. limited pipeline throughput and retry/idempotency
9. ranking that does not sufficiently separate commercial impact from data confidence
10. insufficient automated verification and observability

---

# 3. Implementation Decision Matrix

| Component | Decision | Priority | Required Action |
|---|---|---:|---|
| FastAPI API | KEEP + CHANGE | P1 | Preserve API architecture; expand endpoints and filtering |
| SQLAlchemy 2 | KEEP | P0 | Continue as ORM |
| Alembic | KEEP + CHANGE | P0 | Add incremental migrations for new lifecycle/fingerprint fields |
| PostgreSQL dedicated DB | KEEP | P0 | Preserve strict `competitor_intel` isolation |
| Source registry | KEEP + CHANGE | P0 | Make crawler behavior configurable and source-aware |
| Crawl jobs | KEEP + CHANGE | P0 | Add idempotency, retry, timeout, scheduling metadata |
| Crawl documents | KEEP + CHANGE | P0 | Strengthen canonical URL/hash/version handling |
| Promotion observations | KEEP + CHANGE | P0 | Make observation immutable and traceable to extraction run |
| Promotions | KEEP + CHANGE | P0 | Strengthen canonical identity and lifecycle |
| Promotion evidence | KEEP + CHANGE | P0 | Preserve source-level evidence and extraction location |
| Entity models | KEEP | P0 | Preserve competitor/brand/product/retailer model |
| Entity resolution | **REWRITE** | P0 | Deterministic matching + aliases + review workflow |
| Deduplication | **REWRITE** | P0 | Fingerprint-based promotion identity; never merge distinct mechanics |
| Validation | CHANGE | P0 | Separate field validation from active-status decision |
| LLM extraction | CHANGE | P0 | Runtime date, structured schema, evidence-first extraction |
| Crawler base | CHANGE | P1 | Remove insecure TLS bypass; add robust HTTP handling |
| Superindo crawler | CHANGE | P1 | Keep adapter but move URLs/selectors to source configuration |
| Aggregator crawler | CHANGE | P1 | Replace broad selectors with configurable extraction strategy |
| PDF processing | ADD/CHANGE | P1 | Implement document processor using PDF text extraction |
| OCR | ADD | P1 | Process image/PDF evidence where text is unavailable |
| Playwright | ADD | P1 | Support JS-rendered sources where permitted |
| Source discovery | ADD | P1 | Implement search/discovery layer rather than only fixed URLs |
| Pipeline | CHANGE | P0/P1 | Queue-based, chunked, retryable, idempotent processing |
| Ranking | CHANGE | P2 | Explainable business-impact + data-confidence scoring |
| Review queue | KEEP + CHANGE | P2 | Human review for uncertain entities/promotions |
| Scheduler | CHANGE | P1 | Adaptive source frequency and expiration-aware recrawling |
| Alerting | ADD | P3 | Optional alerts for high-impact/new/changed promotions |
| Observability | ADD | P3 | Health checks, metrics, structured logs |
| Tests | ADD/EXPAND | P0 | Unit + integration + regression tests for critical correctness |

---

# 4. KEEP — Existing Foundation

The following architecture is correct and should remain the foundation.

## 4.1 Dedicated PostgreSQL database

The application must continue using:

```text
competitor_intel
```

It must never depend on `dwh_prod`.

No DWH inspection, cross-database foreign keys, or DWH business logic should be introduced.

## 4.2 Evidence-first data model

The following chain is correct and must be preserved:

```text
crawl_document
      |
      v
promotion_observation
      |
      v
canonical promotion
      |
      v
promotion_evidence
```

A canonical promotion must always be traceable to source evidence.

## 4.3 SQLAlchemy + Alembic

Continue using SQLAlchemy 2 and Alembic. New requirements should be implemented through incremental migrations rather than destructive schema replacement.

## 4.4 FastAPI

Keep FastAPI as the API layer.

## 4.5 Source registry

Keep the source registry as the source-of-truth for crawl configuration, reliability, scheduling, and source metadata.

---

# 5. REWRITE — Deduplication

## Current problem

The current deduplication logic is too weak to safely identify promotions.

A promotion identity cannot be based mainly on retailer, promotion type, active status, and normalized product name.

That can incorrectly merge distinct promotions such as:

```text
Product A — 10% OFF
Product A — Buy 2 Get 1
Product A — Rp20,000 bundle
Product A — Member Price Rp8,000
```

These are different commercial activities even when they concern the same product.

## Required design

Introduce a deterministic promotion fingerprint composed from normalized dimensions such as:

```text
retailer
brand
product / SKU
promotion_type
regular_price
promo_price
discount_percentage
buy_quantity
free_quantity
bundle_quantity
cashback_amount
voucher_amount
minimum_purchase_amount
minimum_purchase_quantity
start_date
end_date
channel
geography
```

Not every field must be present. The fingerprint strategy must support incomplete observations without creating false merges.

The system must distinguish:

```text
same promotion observed again
        !=
new promotion for the same product
```

Observations must remain separate even when they resolve to the same canonical promotion.

## Acceptance criteria

- Re-crawling the same evidence is idempotent.
- Different promotion mechanics are not merged.
- Price changes can create a new observation/version without destroying history.
- Expired promotions remain historically traceable.
- Canonical promotions retain links to all supporting observations/evidence.

---

# 6. REWRITE — Entity Resolution

## Current problem

Current entity resolution is too permissive.

In particular, automatically creating a new retailer when a match is not found can create duplicate or incorrect entities.

## Required behavior

Resolution must use a controlled sequence:

```text
1. exact canonical identifier
2. exact normalized name
3. approved alias
4. high-confidence similarity
5. unresolved / review_required
```

Do not automatically create a new canonical entity merely because similarity failed.

Introduce aliases where useful:

```text
entity_aliases
----------------
entity_type
entity_id
alias
normalized_alias
source_id
is_verified
```

Examples:

```text
PT Indomarco Prismatama
Indomaret
indomaret.co.id
```

can resolve to one approved retailer entity when verified.

## Acceptance criteria

- False entity creation is prevented.
- Ambiguous matches enter `review_queue`.
- Approved aliases improve future resolution.
- Entity resolution is explainable and stores the reason/method used.

---

# 7. CHANGE — Validation

Validation must be separated into two concepts:

### A. Data validity

Checks whether the extracted fields are internally valid.

Examples:

- promo price is not greater than regular price
- percentage is within valid bounds
- quantities are positive
- dates are parseable
- category is supported
- currency is valid

### B. Promotion activity status

Determines whether the promotion should be considered active/upcoming/expired/unknown.

A missing end date must **not** automatically mean indefinitely active.

For example:

```text
start_date <= now
AND end_date >= now
```

is strong evidence of active status.

If `end_date` is missing, recent verification is required according to the product rules.

If dates are ambiguous, the promotion should be `UNKNOWN` or `REVIEW_REQUIRED`, not silently accepted as active.

The validator must preserve uncertainty rather than manufacture dates.

---

# 8. CHANGE — LLM Extraction

## Current risks

The current extractor relies on parsing free-form model output with `json.loads()` and contains a hard-coded current year.

This is fragile.

## Required behavior

The extraction prompt must receive runtime context:

```text
current_datetime
current_date
source metadata
crawl timestamp
published timestamp when available
```

The model must be instructed:

- never invent a price
- never invent a date
- never invent a product/SKU
- return null when evidence is absent
- quote the evidence supporting each important promotional claim
- distinguish explicit source facts from inference

Prefer structured-output/schema enforcement where the configured LLM provider supports it.

If schema enforcement is unavailable, validate the returned JSON against a Pydantic schema before accepting it.

Malformed model output must become a controlled extraction failure/retry rather than silently producing partial canonical data.

---

# 9. CHANGE — Crawler

## Security

The HTTP crawler must not disable TLS certificate verification in production.

Do not use an insecure equivalent of:

```python
verify=False
```

except in an explicitly documented local-development diagnostic mode.

## Source configuration

Source-specific URLs and selectors should move from hard-coded application logic into source configuration wherever practical.

The architecture should support:

```text
source_registry
  -> adapter type
  -> seed URLs
  -> crawl strategy
  -> selectors
  -> pagination rules
  -> rendering requirement
```

The core crawler should remain generic.

## Dynamic pages

Add Playwright support for permitted JavaScript-rendered sources.

## PDFs/images

Add document processing for:

- PDF text
- scanned PDF OCR
- promotional images
- catalog pages

---

# 10. ADD — Source Discovery

The product requirements explicitly call for dynamic discovery.

The system must not depend exclusively on a small list of hard-coded URLs.

Discovery should support combinations such as:

```text
category + promotion keyword + Indonesia
brand + promo
retailer + category + promo
```

Discovery results must pass through the same evidence and validation pipeline as directly configured sources.

Discovery must respect applicable terms, robots rules, rate limits, and source restrictions.

---

# 11. CHANGE — Pipeline

The current pipeline is MVP-oriented and processes only a limited number of documents/cards per run.

That is acceptable for an initial smoke test but not for production intelligence.

The production pipeline must support:

```text
queued
  -> crawling
  -> document processing
  -> extraction
  -> validation
  -> resolution
  -> deduplication
  -> ranking
```

with:

- retries
- exponential/backoff handling where appropriate
- idempotency
- per-stage error state
- dead-letter/review handling
- chunked processing
- concurrency limits
- source-specific rate limiting
- resumability

A single failed document must not stop unrelated processing.

---

# 12. CHANGE — Promotion Lifecycle

Canonical promotions must maintain historical state.

Required conceptual states:

```text
UPCOMING
ACTIVE
EXPIRED
UNKNOWN
REVIEW_REQUIRED
```

Lifecycle decisions must be derived from source observations and timestamps.

The system must support the situation where:

```text
Promotion is active today
       -> later source changes
       -> promotion expires
       -> historical record remains available
```

Do not delete historical observations simply because the promotion is no longer active.

---

# 13. CHANGE — Ranking

The ranking engine should remain explainable.

A recommended conceptual score is:

```text
business_impact
+ promotion_strength
+ category_relevance
+ source_reliability
+ evidence_quality
+ freshness
+ competitor_importance
```

However, **data confidence and business importance must remain distinguishable**.

For example:

```text
Very aggressive promotion + weak source evidence
```

should not automatically outrank:

```text
Moderately aggressive promotion + official retailer evidence
```

Store score components so the Top 10 result can explain why a promotion ranked highly.

---

# 14. CHANGE — Top 10 API

The existing Top 10 concept should remain.

The API should eventually support at least:

```text
GET /promotions/top10
GET /promotions
GET /promotions/{id}
GET /promotions/stats
GET /sources
GET /review-queue
```

The default Top 10 must exclude:

- expired promotions
- stale promotions that fail recency requirements
- unresolved low-confidence records when business rules require review
- promotions without adequate evidence
- obvious duplicates

The API response should expose enough information to explain:

```text
why this promotion is active
why it ranked here
where the evidence came from
when it was last verified
```

---

# 15. ADD — Review Workflow

Human review is required for ambiguous cases rather than forcing the AI to make unsafe decisions.

Examples:

- ambiguous brand
- ambiguous retailer
- uncertain product match
- conflicting dates
- conflicting prices
- low-confidence extraction
- unsupported promotion mechanic
- suspected duplicate

Review decisions should be auditable.

Recommended review outcomes:

```text
APPROVE
REJECT
MERGE
SPLIT
CORRECT
```

---

# 16. Database Migration Requirements

Do not replace the existing schema with a destructive rewrite.

Use incremental Alembic migrations.

The exact migration sequence may evolve, but the target schema must support the following concepts.

## 16.1 Promotion fingerprint

Add a stable fingerprint / identity field to canonical promotions or the appropriate identity table.

Recommended supporting indexes:

```text
promotion fingerprint
status
start_date
end_date
last_seen_at
retailer_id
brand_id
product_id
```

## 16.2 Observation identity

Promotion observations should have a deterministic uniqueness/idempotency strategy based on document/extraction context rather than allowing uncontrolled duplicate observations.

## 16.3 Extraction run

Add an `extraction_runs` concept/table if not already present.

It should record:

```text
id
document_id
model/provider
prompt/schema version
started_at
completed_at
status
raw response reference
error message
created_at
```

This makes AI processing reproducible and auditable.

## 16.4 Entity aliases

Add an alias structure for verified brand/product/retailer mappings.

## 16.5 Resolution metadata

Store how an entity was resolved, for example:

```text
EXACT
NORMALIZED
ALIAS
SIMILARITY
MANUAL
UNRESOLVED
```

and the associated confidence/reason where appropriate.

## 16.6 Evidence strengthening

Evidence should support, where applicable:

```text
page number
image reference
quoted text
source URL
observed timestamp
```

## 16.7 Ranking explanation

Store score components or a structured scoring explanation so ranking can be audited.

## 16.8 Crawl idempotency

Add appropriate unique/indexed identifiers for canonical URL/content hash/source combinations.

Do not over-constrain the schema in a way that prevents legitimate historical versions of a changing page.

---

# 17. Required Indexing

At minimum, evaluate indexes for:

```text
source_registry(domain)
source_registry(is_active)
crawl_jobs(source_id, status)
crawl_jobs(created_at)
crawl_documents(source_id, canonical_url)
crawl_documents(content_hash)
promotion_observations(document_id)
promotion_observations(observed_at)
promotions(status, end_date)
promotions(last_seen_at)
promotions(retailer_id)
promotions(brand_id)
promotions(product_id)
promotion_evidence(promotion_id)
review_queue(status, created_at)
```

Use `pg_trgm` indexes for approved similarity-search use cases.

---

# 18. Data Integrity Rules

The implementation must follow these rules:

1. No canonical promotion without traceable evidence.
2. No generated price where the source did not provide one.
3. No generated promotion date where the source did not provide one.
4. No silent entity creation caused by failed matching.
5. No automatic merge of materially different promotions.
6. No deletion of historical observations merely because a promotion expired.
7. No cross-database dependency on `dwh_prod`.
8. No production TLS verification bypass.
9. No hard-coded current date/year in extraction logic.
10. No single-document failure may stop the entire crawl pipeline.

---

# 19. Testing Requirements

Before considering the implementation production-ready, add tests for at least:

## Deduplication

- same promotion / same observation
- same promotion / different crawl
- different mechanic / same product
- changed price
- changed validity period
- different retailer
- different geography

## Entity resolution

- exact match
- normalized match
- approved alias
- high similarity
- ambiguous similarity
- unknown entity

## Validation

- valid discount
- invalid discount
- promo price greater than regular price
- missing end date
- expired promotion
- future promotion
- malformed date
- unsupported category

## Extraction

- valid structured response
- malformed JSON
- missing fields
- conflicting evidence
- model refusal/error
- runtime date handling

## API

- Top 10 only returns eligible records
- expired records excluded
- stale records excluded
- evidence included
- ranking order deterministic

## Pipeline

- retry after transient failure
- one failed document does not abort batch
- duplicate document is idempotent
- failed extraction can be retried

---

# 20. Operational Requirements

Production deployment should provide:

- `/health` endpoint
- database connectivity check
- structured application logs
- crawl success/failure metrics
- extraction success/failure metrics
- queue depth metrics when queues are introduced
- retry counters
- review queue size
- last successful crawl per source
- alerting for repeated source failures

The scheduler should use source-specific frequencies from `source_registry` and increase verification frequency as promotions approach expiry, within practical rate limits.

---

# 21. What Must NOT Be Added

The following are explicitly prohibited unless the product scope is deliberately changed:

- dependency on `dwh_prod`
- DWH schema inspection
- DWH foreign keys
- copying DWH tables into this project merely for convenience
- credentials allowing the application to access unrelated databases
- fabricated promotion facts
- blind AI acceptance without validation
- destructive replacement of the existing schema
- production TLS certificate bypass
- uncontrolled scraping that ignores source restrictions

---

# 22. Implementation Order

Implementation should proceed in this order.

### Phase P0 — Correctness

1. Deduplication rewrite
2. Entity-resolution rewrite
3. Promotion lifecycle/status rules
4. Evidence integrity
5. Validation improvements
6. Extraction schema/runtime-date improvements
7. Idempotent pipeline behavior
8. Critical automated tests

### Phase P1 — Collection

1. Document processor
2. PDF extraction
3. OCR
4. Playwright where required
5. Source discovery
6. Configurable source adapters
7. Retry/rate limiting
8. Adaptive scheduler

### Phase P2 — Intelligence

1. Explainable ranking
2. Review workflow
3. Entity aliases
4. Confidence model
5. Promotion change/version detection

### Phase P3 — Product

1. Expanded REST API
2. Statistics/trends
3. Dashboard integration
4. Alerts

### Phase P4 — Production Hardening

1. Observability
2. Health checks
3. Integration tests
4. Docker Compose application services
5. Deployment/runbook
6. Backup/recovery procedures

---

# 23. Definition of Done

The implementation is considered aligned with the requirements when all of the following are true:

- [ ] Product requirements are represented in `FMCG Competitor Promotion.md`.
- [ ] Technical architecture is represented in `TECHNICAL_DESIGN.md`.
- [ ] This document accurately records implementation gaps and required changes.
- [ ] `master` is the authoritative source of truth.
- [ ] PostgreSQL application isolation is preserved.
- [ ] Every canonical promotion has source evidence.
- [ ] Deduplication does not merge distinct promotions.
- [ ] Entity resolution does not create unsafe duplicate entities.
- [ ] Promotion lifecycle is deterministic and evidence-based.
- [ ] LLM extraction is schema-validated and does not depend on a hard-coded year.
- [ ] Crawling supports static and required dynamic/document sources.
- [ ] Pipeline processing is retryable and idempotent.
- [ ] Top 10 ranking is explainable.
- [ ] Review-required cases are visible to humans.
- [ ] Critical behavior has automated tests.
- [ ] Operational health and failures are observable.

---

# 24. Synchronization Rule

Whenever implementation changes, one of these documents must be updated in the same change when the change affects requirements or architecture:

```text
FMCG Competitor Promotion.md
TECHNICAL_DESIGN.md
IMPLEMENTATION_ALIGNMENT.md
```

Code must not silently diverge from the documented architecture.

If a requirement is intentionally changed, update the documentation first or in the same commit and record the reason.

If implementation reveals a new bug, limitation, or architectural requirement, record it here before or together with the implementation change.

**This document is the bridge between the PRD, technical design, and actual codebase.**
