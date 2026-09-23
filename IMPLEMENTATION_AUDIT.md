# IMPLEMENTATION_AUDIT.md — Pre-Implementation Architecture Audit

## Purpose

This document compares the current repository implementation on `docs/production-architecture-v2` with the frozen documentation set.

**Status: PHASE 0 IN PROGRESS — database/source/geography foundations landed; orchestration and quality-gate work remain.**

The repository already contains a useful MVP vertical slice, but several implementation details contradict the new multi-source, geography-first, evidence-first architecture. These must be corrected before production implementation.

## Executive result

| Area | Current state | Required state | Action |
|---|---|---|---|
| PostgreSQL boundary | Correct database/schema configuration is present | Keep isolated `competitor_intel`; never touch `dwh_prod` | KEEP + TEST |
| Source registry | Exists | Add access mode/status, health, adapter and URL registry | CHANGE |
| URL registry | Missing as a first-class table/model | Required | ADD |
| Source discovery | Not implemented as a separate workflow | Candidate → assess → approve | ADD |
| Crawler scheduling | Runs every active source | Crawl due approved URL targets | REWRITE |
| Crawler access | HTTP only in base crawler; browser not integrated | HTTP + browser adapter when public JS requires it | CHANGE |
| Source adapters | Hard-coded Hemat/Superindo + generic aggregator fallback | Adapter registry and source-specific strategies | REWRITE |
| Promotion geography | Single `geography` string and default Indonesia | Relational inclusion/exclusion geography | REWRITE |
| Verification timestamp | API uses `last_seen_at` as verification | Separate `last_verified_at` | ADD |
| Regional pricing | Not modeled | Geography + retailer/channel + observation | REWRITE |
| Prices | PostgreSQL FLOAT | NUMERIC(18,2) | MIGRATE |
| Promotion dedup | Product + retailer + type + ACTIVE only | Product + retailer + channel + mechanic + price + geography + validity + conditions | REWRITE |
| Multi-source evidence | Evidence attaches to promotion, but merge logic can overwrite facts | Preserve source observations and conflicts | CHANGE |
| Active status | Created as ACTIVE without full current-validity gate | Derive/validate against validity + freshness | REWRITE |
| 90-day rule | Configuration exists, but current API logic is not sufficient | Explicit freshness quality gate | CHANGE |
| UI | PostgreSQL/API-backed | Keep, but add geography/source health/discovery/review workflows | CHANGE |
| Mock data | Dashboard appears API-backed | Keep no-mock rule and add tests | KEEP + TEST |
| Seed data | Hard-coded sources and products | Seed only approved initial configuration; no fake promotion facts | CHANGE |
| Tests | Architecture requires them | Add migration, integration, crawler and quality-gate tests | ADD |

### Phase 0 implementation checkpoint

Completed on this branch:

- source registry now carries lifecycle/access state and crawl health counters.
- source_urls is a first-class persisted crawl-target registry.
- crawl jobs can reference a registered URL target.
- geography is modeled relationally through geographies and promotion_geographies.
- source geography wording is retained on the promotion-geography relation; missing geography is not defaulted to Indonesia.
- canonical promotions now separate last_seen_at from last_verified_at.
- observations carry verification/quality state and validity dates.
- evidence can point back to the immutable observation that produced it.
- monetary promotion fields use PostgreSQL NUMERIC.
- the first Alembic migration bootstraps an empty competitor_intel database from the declarative schema.

Still required before production crawling:

- replace source-level crawler orchestration with due source_urls scheduling.
- implement explicit adapter selection and browser fallback.
- implement deterministic quality gate.
- rewrite deduplication around material commercial dimensions.
- migrate/update existing seed data and API contracts.
- add database/integration/source-fixture tests.
- run migration and application tests against a clean PostgreSQL competitor_intel database.

## 1. Database and schema

### Current

The application session uses:

`postgresql+psycopg://.../competitor_intel`

with search path `competitor_intel,public`.

This is aligned with the architecture.

### Required

Add an automated test that fails if the configured database name or current database is `dwh_prod`.

The application must never use cross-database references.

**Action: KEEP + TEST.**

## 2. Source registry

### Current

`SourceRegistry` exists, but it has only:

- domain
- base URL
- source type
- tier
- reliability
- crawl frequency
- priority
- active flag
- robots flag
- basic timestamps

### Problem

The new source strategy requires explicit:

- access mode
- access status
- adapter key
- assessment state
- discovery timestamps
- failure/backoff information
- source health

`robots_allowed` alone is not an adequate access policy state.

### Action

Migrate `source_registry` to support:

`DISCOVERED, CANDIDATE, ASSESSED, APPROVED, ACTIVE, WARNING, STALE, BLOCKED, DISABLED, MANUAL_ONLY`

and access states such as:

`HTTP, BROWSER, PUBLIC_API, FEED, SITEMAP, MANUAL`

plus:

`LOGIN_REQUIRED, CAPTCHA_REQUIRED, PAYWALL, BLOCKED, RATE_LIMITED`

where applicable.

## 3. URL registry

### Current

There is no first-class `source_urls` model/table.

Crawler targets are hard-coded inside crawler classes.

### Problem

This directly conflicts with the requirement that the next normal run should use the approved website inventory stored in PostgreSQL.

### Required

Create `source_urls` with:

- source_id
- URL
- canonical_url
- page_type
- category_hint
- crawl_priority
- crawl_frequency_minutes
- active flag
- last crawled
- last success
- HTTP status
- content hash
- failure count
- next crawl time

### Action

**ADD before expanding source count.**

## 4. Crawler manager

### Current

`run_all_crawlers()` loads every active source and invokes a crawler for each one.

### Problem

This is source-level scheduling, not URL-level scheduling.

It also means a source can be crawled even when none of its targets is due.

### Required

The scheduler should:

1. load approved active sources
2. load active URL targets due for crawl
3. select the correct adapter
4. crawl only due targets
5. record success/failure
6. apply backoff
7. update next crawl time

### Action

**REWRITE.**

## 5. Hard-coded URLs

### Current

Hemat and Superindo URLs are embedded directly in Python classes.

### Problem

Adding a URL requires code changes and deployment.

### Required

Move URLs into `source_urls`.

Source adapters may provide discovery rules/defaults, but production crawl targets are persisted configuration.

### Action

**REWRITE.**

## 6. Public JavaScript/browser support

### Current

The base crawler uses `httpx`.

There is no demonstrated Playwright execution path in the inspected crawler implementation.

### Problem

Some public retailer/e-commerce pages require JavaScript rendering.

### Required

Support:

- HTTP first
- browser fallback when source configuration says JS is required
- public browser-visible content only
- no authentication/CAPTCHA/paywall/access-control bypass

### Action

**ADD browser-capable crawler adapter and tests.**

## 7. Source adapter selection

### Current

Unknown sources fall back to `AggregatorCrawler`.

### Problem

This can cause unrelated websites to be parsed using the wrong extraction strategy.

### Required

Use explicit adapter keys:

`HEMAT`, `RETAILER`, `BRAND`, `MARKETPLACE`, `NEWS`, etc.

Unsupported sources should be marked unsupported/manual rather than silently treated as aggregators.

### Action

**REWRITE.**

## 8. Geography

### Current

`Promotion.geography` is a single string with default `Indonesia`.

The deduplicator also writes `geography="Indonesia"` for every new promotion.

### Problem

This is a critical architecture bug.

A promotion explicitly limited to Jawa, Jabodetabek, Palembang or selected stores can be incorrectly represented as nationwide.

### Required

Create a geography reference model and promotion geography relation with:

- normalized geography
- source wording
- inclusion/exclusion role
- scope type
- confidence
- optional parent geography

Do not infer missing geography as Indonesia.

### Action

**REWRITE before production data is accepted.**

## 9. Regional pricing

### Current

There is no relational regional price observation model.

### Problem

The same SKU can legitimately have different prices by geography, retailer or channel.

### Required

The observation/canonical structure must allow:

`product + retailer + channel + geography + promotion conditions + validity + price`

to form a materially distinct commercial observation.

### Action

**ADD/REWRITE.**

## 10. Verification timestamps

### Current

The API exposes `last_seen_at` as `last_verified`.

### Problem

These are not equivalent.

A crawl can see a page without validating all commercial facts.

### Required

Add:

- first_seen_at
- last_seen_at
- last_verified_at
- valid_from
- valid_until

Only `last_verified_at` should satisfy the verification freshness rule.

### Action

**ADD + API CHANGE.**

## 11. Promotion deduplication

### Current

The deduplicator searches active promotions using retailer and promotion type, then compares normalized product names.

It may update the existing promotion's price and discount when a new source observation arrives.

### Problem

This can incorrectly merge:

- different regions
- different channels
- different prices
- different validity periods
- different promotion conditions
- different source observations

It can also silently overwrite a commercially meaningful value.

### Required

Dedup identity must include, as appropriate:

- product/SKU
- retailer
- channel
- mechanic
- mechanic parameters
- geography
- price/price condition
- validity
- minimum purchase
- member condition
- other material conditions

Observations remain immutable. Canonical records may be reconciled without destroying the underlying observations.

### Action

**REWRITE.**

## 12. Price data type

### Current

Promotion prices, discount values and product pack values use PostgreSQL FLOAT.

### Problem

Money should not use binary floating-point storage.

### Required

Use `NUMERIC(18,2)` for monetary amounts and appropriate numeric types for percentages/quantities.

### Action

**MIGRATION REQUIRED.**

## 13. Active promotion status

### Current

New promotions are saved as `ACTIVE`.

### Problem

The current persistence path does not prove that:

- valid_from has started
- valid_until has not expired
- evidence exists
- the source is approved
- the observation is fresh enough
- identity is sufficiently resolved

### Required

Use deterministic quality/status evaluation.

An explicit expired `valid_until` always wins over crawl freshness.

### Action

**REWRITE quality gate.**

## 14. Top 10 freshness

### Current

The application has `RECENCY_MONTHS=3`, but the inspected promotion model/API relies primarily on status and last-seen behavior.

### Required

Default Top 10 eligibility must enforce:

- commercially active
- `last_verified_at >= now - 90 days`
- evidence exists
- approved source
- sufficient identity/geography quality
- no material unresolved contradiction

### Action

**CHANGE API query + quality service + tests.**

## 15. Evidence

### Current

Evidence is attached to canonical promotions.

### Good

This is useful and should remain.

### Problem

The observation layer needs stronger linkage between extracted fields and source documents. Evidence must not become the only historical representation of source observations.

### Required

Keep immutable `promotion_observations`, then derive canonical promotions and evidence relationships.

### Action

**CHANGE, not remove.**

## 16. Source seeding

### Current

`seed_data.py` seeds several retailers and sources, including Hemat.id, Superindo, KlikIndomaret, Alfagift and a promotion aggregator.

### Problem

Some URLs are hard-coded and source approval state is represented only by `is_active`.

The seed data also assigns large static product catalogs and default pack sizes. These are master-data seeds, not source observations, and must never be presented as discovered promotions.

### Required

Separate:

- reference master data
- source configuration
- crawl targets
- observed commercial data

Seed only known reference facts and approved source configuration.

### Action

**CHANGE.**

## 17. Pipeline

### Current

`run_pipeline()` can call all active crawlers and then process the latest documents.

### Problem

The extraction loop assumes catalog blocks split by `---`, which is source-specific and not safe as a global extraction strategy.

### Required

Source adapter → normalized document → extraction units → structured extraction.

Extraction units must be source-aware.

### Action

**REWRITE pipeline orchestration, retain reusable extraction service.**

## 18. Dashboard

### Current

The dashboard already queries API endpoints rather than embedding production promotion rows.

This is a good foundation.

### Required UI additions

- geography filter
- source filter
- verification age
- source health
- Scan now
- Discover sources
- review queue
- regional price comparison
- evidence/source drawer
- explicit empty/error/stale states

The current UI's overall table/drawer approach can be retained and refined.

### Action

**KEEP FOUNDATION + CHANGE.**

## 19. API

### Current

Promotion detail and stats endpoints exist.

### Required

Add/align:

- geography
- source
- last_verified_at
- evidence verification status
- source health
- source registry
- URL targets
- review queue
- discovery status

### Action

**CHANGE.**

## 20. Required implementation order

Do not add many new crawlers yet.

### Phase 0 — Architecture correction

1. Source state/access model
2. URL registry
3. Geography model
4. Observation/canonical separation
5. NUMERIC money migration
6. verification timestamps
7. quality gate
8. safe deduplication
9. tests

### Phase 1 — Real-data vertical slice

```
One approved source
    ↓
registered URL
    ↓
crawl
    ↓
document
    ↓
extraction
    ↓
observation
    ↓
geography
    ↓
validation
    ↓
canonical promotion
    ↓
evidence
    ↓
API
    ↓
UI
```

### Phase 2 — Additional official sources

Add selected retailer/brand adapters.

### Phase 3 — Discovery

Add candidate-source discovery and assessment.

### Phase 4 — Marketplace/e-commerce

Add individually assessed public sources and browser adapters where appropriate.

## 21. Definition of done before production crawling

- [x] `source_urls` exists
- [x] source lifecycle exists
- [x] access status exists
- [ ] browser adapter exists where needed
- [x] geography is relational
- [ ] regional prices remain distinct
- [x] `last_verified_at` exists
- [x] money uses NUMERIC
- [x] observations are immutable
- [ ] dedup key includes material commercial dimensions
- [ ] failed crawl != zero promotions
- [ ] explicit expiry wins
- [ ] 90-day freshness is enforced
- [ ] evidence is mandatory for verified records
- [ ] API uses PostgreSQL
- [ ] UI uses API only
- [ ] dwh_prod access test exists
- [ ] source adapter fixtures exist
- [ ] integration tests pass
- [ ] no hard-coded production crawl URL is required for normal operation

## 22. Decision

The current repository is a useful MVP foundation, but **it should not be extended by adding more crawler classes yet**.

First correct the source registry, URL registry, geography, observation/deduplication and quality-gate foundations. Then implement one real end-to-end source and use that vertical slice as the acceptance test for every subsequent source.
