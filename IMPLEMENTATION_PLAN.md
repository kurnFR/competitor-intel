# IMPLEMENTATION_PLAN.md — Production Execution Plan

## 1. Purpose

This is the master execution plan for the FMCG Competitor Promotion Intelligence Platform.

The planning documents define the target architecture; this file defines the order in which that architecture is implemented, the dependencies between phases, and the exit gate required before the next phase is treated as production-ready.

**Rule:** implementation must follow the phase gates below. A phase may contain multiple commits, but work should not silently bypass an exit gate.

The PostgreSQL database is the application source of truth. The platform is multi-source, geography-first, evidence-first, and designed for compliant collection of public information.

## 2. Current baseline

Branch: `docs/production-architecture-v2`

The repository already contains a partial vertical slice covering:

- dedicated `competitor_intel` database/schema configuration
- source registry and source URL registry
- crawl health/backoff fields
- explicit source adapter keys
- HTTP crawling and permitted browser-mode support
- change detection
- AI extraction schemas
- deterministic extraction/deduplication foundations
- relational geography and regional price observations
- evidence linkage
- review decisions and audit trail
- Top 10 API eligibility gates
- initial dashboard/API structure
- Alembic bootstrap plus follow-on migrations

This is **not yet production complete**. Tests have not been successfully executed against a clean PostgreSQL environment in the current development environment.

## 3. Phase map

| Phase | Name | Primary outcome | Current state |
|---|---|---|---|
| 0 | Foundation | isolated DB, migrations, config, baseline tests | PARTIAL / IN PROGRESS |
| 1 | Discovery & Registry | approved source + URL control plane | PARTIAL |
| 2 | Crawling & Change Detection | due-target scheduling and reliable retrieval | PARTIAL |
| 3 | Extraction & Validation | source-specific extraction with deterministic quality gates | PARTIAL |
| 4 | Observation & Canonicalization | immutable observations and material commercial identity | PARTIAL |
| 5 | Geography & Regional Pricing | trustworthy regional/channel price and scope handling | PARTIAL |
| 6 | Ranking / Top 10 | explainable, eligible active activity ranking | PARTIAL |
| 7 | Review Workflow | evidence-based human review and audit | PARTIAL |
| 8 | API Contracts | stable production API and contract tests | PARTIAL |
| 9 | Dashboard / UI | professional API-backed operating dashboard | PARTIAL |
| 10 | Production Operations | scheduler, monitoring, retries, alerts, backup/runbook | NOT COMPLETE |
| 11 | Testing & Hardening | unit, fixture, integration, E2E, security and load coverage | NOT COMPLETE |
| 12 | Production Readiness | deployable, observable, recoverable production system | NOT COMPLETE |

## 4. Phase 0 — Foundation

### Objective

Establish a clean and isolated application foundation before source expansion.

### Scope

- dedicated `competitor_intel` database
- `competitor_intel` schema
- least-privilege application role
- Alembic migration chain
- configuration and environment validation
- no dependency on `dwh_prod`
- baseline model/import tests

### Exit gate

All of the following must be demonstrated on a clean database:

1. `alembic upgrade head` succeeds.
2. Required schema/tables exist.
3. Application connects using the intended database and schema.
4. Application role does not require destructive/admin privileges.
5. No cross-database dependency exists.
6. Money fields use `NUMERIC(18,2)`.
7. Migration history is linear and safe for a fresh install.
8. Baseline tests run successfully.

### Required evidence

- migration output
- database/schema verification
- automated tests
- migration review

---

## 5. Phase 1 — Source Discovery & Registry

### Objective

Make source discovery and crawl targeting configuration-driven.

### Scope

Source lifecycle:

`DISCOVERED -> CANDIDATE -> ASSESSED -> APPROVED -> ACTIVE`

Operational states may include `WARNING`, `STALE`, `BLOCKED`, `DISABLED`, and `MANUAL_ONLY`.

Access modes/statuses must distinguish permitted public access from restricted access.

The URL registry must own:

- URL/canonical URL
- source
- page type/category
- priority
- frequency
- active state
- last crawl/success
- status
- content hash
- failure count
- next crawl time

### Rules

- Normal scheduled runs crawl approved active URL targets already in PostgreSQL.
- Discovery is a separate workflow.
- Discovered sources are never automatically trusted.
- Unsupported adapters must fail explicitly or enter manual review.
- No access-control bypass.

### Exit gate

1. Candidate source can be discovered and stored without activation.
2. Assessment can approve/reject a candidate.
3. Approved source can have multiple URL targets.
4. A URL can be disabled independently.
5. Historical observations survive source/URL disablement.
6. Scheduler selection can be restricted to approved/active sources and due targets.
7. Adapter assignment is explicit.

---

## 6. Phase 2 — Crawling & Change Detection

### Objective

Reliably collect permitted public content only when a registered target is due.

### Scope

- due-target scheduler
- HTTP-first retrieval
- browser fallback for configured public JS pages
- crawl jobs/documents
- content hashing
- unchanged/changed detection
- bounded retry/backoff
- source and URL health
- blocked/restricted handling

### Rules

A failed crawl is not zero promotions.

An unchanged document should skip expensive extraction when the adapter can safely establish that the relevant content is unchanged.

Browser automation must not bypass login, CAPTCHA, paywall, private APIs or other access controls.

### Exit gate

1. Only due approved targets are crawled.
2. Success and failure are persisted.
3. Failure increases bounded backoff.
4. Successful zero-result crawl remains a successful crawl.
5. Unchanged content is detectable and can skip extraction.
6. Changed content produces a new document/extraction path.
7. Blocked/restricted sources stop automatic retry according to policy.
8. Browser mode works against a permitted fixture/source.
9. TLS verification is enabled for normal HTTP retrieval.

---

## 7. Phase 3 — Extraction & Validation

### Objective

Convert source documents into structured candidate observations without inventing facts.

### Scope

- source-specific adapters
- extraction schemas
- AI extraction
- schema/version tracking
- deterministic validation
- field-level confidence
- unknown/null preservation
- extraction failure handling

### Minimum extracted dimensions

Product/SKU, brand, competitor, category, pack size, regular price, promo price, discount, mechanic, mechanic parameters, retailer, channel, geography wording, validity, conditions, evidence quote.

### Rules

- AI proposes facts; deterministic validation decides whether facts are acceptable.
- Missing information stays unknown.
- Source wording is preserved.
- Extraction failure preserves the source document and does not create a synthetic promotion.

### Exit gate

1. Each supported source has representative fixtures.
2. Fixture extraction is deterministic enough for regression testing.
3. Invalid dates/prices/mechanics fail validation.
4. Missing geography is not converted to nationwide.
5. Evidence text is retained.
6. Extraction model/schema versions are persisted.
7. Failed extraction is observable and retryable.

---

## 8. Phase 4 — Observation & Canonicalization

### Objective

Separate immutable source observations from canonical commercial activities.

### Scope

- immutable `promotion_observations`
- canonical promotions
- evidence linkage
- entity resolution
- material deduplication
- conflict retention
- observation verification state

### Material identity

Matching must consider the commercial dimensions that can change the activity, including where applicable:

- product/SKU
- retailer
- channel
- promotion mechanic
- mechanic parameters
- geography
- price/price condition
- validity
- minimum purchase
- member/customer condition
- other material terms

### Rules

Two observations may describe the same activity, but source observations must not be destroyed.

Different regional/channel/material conditions must not be merged merely because product names match.

### Exit gate

1. Observations are immutable.
2. Evidence links to the observation/source document.
3. Materially different activities remain distinct.
4. Repeated observations update canonical freshness without overwriting historical evidence.
5. Source conflicts remain inspectable.
6. Dedup regression tests cover regional/channel/price/mechanic/validity differences.

---

## 9. Phase 5 — Geography & Regional Pricing

### Objective

Make geography and price scope trustworthy enough for regional commercial decisions.

### Scope

- normalized geography reference
- source geography wording
- inclusion/exclusion semantics
- parent geography where supported
- regional price observations
- retailer/channel-specific pricing
- validity and verification timestamps

### Rules

- Never default unknown geography to Indonesia.
- Never expand marketing language such as `Jawa` or `Jabodetabek` into administrative units without an approved mapping.
- A price is contextual: product + retailer + channel + geography + conditions + validity.
- Exact source wording remains available for audit.

### Exit gate

1. Regional and national scope can coexist.
2. Inclusion/exclusion is represented.
3. Unknown geography remains unknown.
4. Same SKU with different regional prices remains separately queryable.
5. Regional price evidence includes source URL and capture/verification timestamps.
6. API/UI can distinguish regional values without false nationwide aggregation.

---

## 10. Phase 6 — Ranking / Top 10

### Objective

Return only currently eligible activities and rank them using an explainable score.

### Default eligibility

- commercially active
- explicit expiry not passed
- `last_verified_at` within configured freshness window (default 90 days)
- evidence exists
- source is approved/active
- quality gate passed
- identity sufficiently resolved
- geography sufficiently understood
- no material unresolved contradiction

### Ranking

Use configurable, explainable factors such as:

- promotion strength
- price impact
- source authority
- verification recency
- geographic/reach scope
- strategic relevance

The score must expose its factors; it must not be an opaque arbitrary number.

### Exit gate

1. Expired activities never appear as active.
2. Old unverified activities are excluded by default.
3. Evidence/source traceability is required.
4. Regional scope is respected.
5. Score factors are deterministic and inspectable.
6. Top 10 has regression fixtures for eligibility edge cases.

---

## 11. Phase 7 — Review Workflow

### Objective

Provide controlled human review for low-confidence, conflicting or incomplete commercial facts.

### Scope

- review queue
- evidence viewer
- approve/reject/request-correction decisions
- reviewer and timestamp
- reason/audit trail
- reprocessing path

### Rules

Approval cannot manufacture missing evidence.

### Exit gate

1. A pending record can be reviewed from its evidence.
2. Decision is persisted with reviewer/time/reason.
3. Approval requires sufficient evidence.
4. Rejection does not delete the original observation.
5. Review decisions are auditable.
6. Re-review/reprocessing is possible without data loss.

---

## 12. Phase 8 — API Contracts

### Objective

Stabilize backend contracts before UI hardening.

### Minimum endpoints

- `GET /health`
- `GET /api/v1/promotions/top10`
- `GET /api/v1/promotions/{promotion_id}`
- `GET /api/v1/stats/`
- `GET /api/v1/sources/health`
- regional pricing endpoint
- review endpoint
- source registry endpoint

### Requirements

- filtering
- pagination where needed
- stable status semantics
- explicit empty/error/stale states
- traceable source/evidence fields
- no mock fallback

### Exit gate

1. OpenAPI/schema contracts match implementation.
2. Contract tests cover success, empty, invalid-filter and error cases.
3. API values are sourced from PostgreSQL.
4. Top 10 and detail endpoints agree on eligibility semantics.
5. Source health and review APIs expose operational state.

---

## 13. Phase 9 — Dashboard / UI

### Objective

Deliver the professional operating dashboard defined in the UX design.

### Navigation

Overview, Promotions, Regional Pricing, Competitors, Sources, Review Queue, Settings.

### Core UI

- KPI overview
- Top 10 / active promotions
- filterable promotion table
- right-side detail drawer
- regional price comparison
- competitor comparison
- source health
- evidence viewer
- review queue

### Required filters

Geography, source, retailer, category, brand, competitor, promotion type/mechanic, channel, status and validity/verification age.

### Rules

Refresh, Scan now and Discover sources remain distinct actions.

No hard-coded promotion rows, demo JSON or synthetic fallback records.

### Exit gate

1. Every displayed promotion can be traced through API to PostgreSQL evidence.
2. Empty database has an explicit empty state.
3. Crawl/source failure has an explicit stale/error state.
4. Filters map to backend data.
5. Regional differences are visible.
6. Evidence and source URL are accessible from detail.
7. Review workflow is usable end-to-end.
8. No production data is duplicated as frontend fixtures.

---

## 14. Phase 10 — Production Operations

### Objective

Operate the pipeline continuously and safely.

### Scope

- scheduler
- adaptive crawl frequency
- retry/backoff
- source health
- alerts
- structured logs
- metrics
- run identifiers
- operational review items
- backups
- retention
- deployment/runbook automation

### Adaptive scheduling inputs

Source priority, historical yield, change frequency, freshness, validity windows and recent failures.

Initial policy may use shorter intervals for high-value frequently changing pages and longer intervals for catalogs/static pages, with configuration rather than hard-coded business logic.

### Exit gate

1. Scheduled cycles run without manual intervention.
2. Failed targets back off.
3. High-value sources are refreshed according to policy.
4. Stale/blocked sources are observable.
5. Alerts exist for material pipeline failures.
6. Logs correlate source -> URL -> crawl -> document -> extraction -> observation.
7. Backup/restore procedure is documented and tested.

---

## 15. Phase 11 — Testing & Hardening

### Required test layers

### Unit

Models, validators, geography normalization, dedup identity, eligibility, scoring, backoff.

### Fixture

Each source adapter has representative HTML/JSON/PDF/browser fixtures.

### Integration

Clean PostgreSQL migration, seed, crawl persistence, extraction, canonicalization, API.

### End-to-end

Approved source -> crawl -> document -> extraction -> observation -> canonical promotion -> API -> UI.

### Security

- secret/config checks
- database least privilege
- no `dwh_prod` access
- SSRF controls for discovered URLs
- safe URL canonicalization
- no access-control bypass paths
- dependency/security scanning

### Load/reliability

- repeated scheduled cycles
- duplicate source documents
- large review queues
- concurrent API reads
- retry storms/backoff behavior

### Exit gate

All required automated tests pass in CI and the clean-database integration suite is reproducible.

---

## 16. Phase 12 — Production Readiness

### Objective

Confirm the complete system is deployable, observable, recoverable and safe.

### Production checklist

- [ ] clean migration
- [ ] least-privilege DB roles
- [ ] environment/secrets configured outside Git
- [ ] approved source registry
- [ ] approved URL registry
- [ ] source adapter fixtures
- [ ] scheduler enabled
- [ ] monitoring/alerts enabled
- [ ] backup verified
- [ ] restore drill completed
- [ ] API contract tests passing
- [ ] UI E2E checks passing
- [ ] source health visible
- [ ] review queue visible
- [ ] Top 10 eligibility verified
- [ ] no mock/fallback promotion data
- [ ] public-collection/access-control policy reviewed
- [ ] runbook current
- [ ] rollback procedure documented

### Final production acceptance

A production release is accepted only when a real approved source can be followed end-to-end:

`registered target -> scheduled crawl -> successful retrieval -> extraction -> validation -> observation -> evidence -> canonical activity -> eligibility -> API -> UI`

and failure/blocked/expired/regional cases are demonstrably handled without inventing or silently destroying facts.

## 17. Change-control rule

When implementation reveals a genuine architectural gap:

1. update the relevant planning document first;
2. update this phase plan if sequencing or acceptance criteria change;
3. implement the code/migration;
4. add or update tests;
5. update `IMPLEMENTATION_AUDIT.md` with actual status.

Do not silently change production behavior only in code.

## 18. Current implementation priority

The next build sequence after this planning baseline is:

1. finish/reconcile Phase 0 migration and test foundations;
2. finish Phase 1 source discovery/registry contracts;
3. finish Phase 2 due-target crawling and change detection;
4. finish Phase 3 source fixtures and validation;
5. finish Phase 4 canonicalization/dedup/conflict handling;
6. finish Phase 5 geography/regional pricing;
7. finish Phase 6 ranking;
8. finish Phase 7 review;
9. stabilize Phase 8 API;
10. harden Phase 9 UI;
11. implement Phase 10 operations;
12. execute Phase 11 hardening;
13. run Phase 12 production acceptance.

**Do not expand source coverage simply because a crawler can fetch a site. Source coverage expands only after the source/adapter/fixture/quality gates above are satisfied.**
