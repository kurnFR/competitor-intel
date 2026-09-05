# Implementation File Plan

## Purpose

This document converts the Product Requirements Document (`FMCG Competitor Promotion.md`), `TECHNICAL_DESIGN.md`, and `IMPLEMENTATION_ALIGNMENT.md` into an implementation-level plan.

It is the execution map for bringing `master` into alignment with the agreed architecture. It does **not** replace the PRD or technical design.

## Document authority

When requirements appear to conflict, use this order:

1. Product/business requirements in `FMCG Competitor Promotion.md`.
2. Architecture and technical constraints in `TECHNICAL_DESIGN.md`.
3. Implementation decisions and migration sequencing in `IMPLEMENTATION_ALIGNMENT.md` and this file.
4. Existing code is evidence of the current implementation, not authority over requirements.

The project must remain incremental. Existing working components should be retained where they already satisfy the architecture; correctness problems should be repaired rather than hidden by a full rewrite.

## Target architecture

```text
Public Sources
    -> Source Registry
    -> Crawl Job
    -> Crawl Document
    -> Document Processing / OCR
    -> Promotion Observation
    -> Structured AI Extraction
    -> Validation
    -> Entity Resolution
    -> Deduplication / Promotion Identity
    -> Canonical Promotion
    -> Evidence
    -> Ranking
    -> Review / Approval when required
    -> API / Dashboard / Alerts
```

The key architectural rule is that an **observation is not automatically a canonical promotion**. Source evidence remains traceable, while multiple observations may update the same canonical promotion only when the promotion identity rules prove that they represent the same commercial offer.

## File-level implementation matrix

| Area / file | Action | Required change |
|---|---|---|
| `app/services/deduplication/deduplicator.py` | **REWRITE** | Replace retailer + promotion-type + product substring matching with a deterministic promotion fingerprint/identity strategy. Never merge distinct promotions merely because they share a product and promotion type. Preserve observation-to-promotion linkage and evidence history. Make writes idempotent. |
| `app/services/entity_resolution/resolver.py` | **REWRITE** | Introduce normalized aliases, candidate generation, scored matching, confidence thresholds, ambiguity handling, and review state. Do not silently create a new retailer/entity from a weak match. Unresolved entities must remain explicitly unresolved. |
| `app/services/validation/validator.py` | **CHANGE** | Separate field/data validation from promotion lifecycle/status. Reject impossible commercial values, retain explicit uncertainty for malformed/missing dates, validate discount consistency, and distinguish invalid data from data that simply needs review. |
| `app/services/extraction/llm_extractor.py` | **CHANGE** | Use the runtime date rather than a hardcoded year. Prefer strict structured/schema-constrained output. Preserve extraction metadata and evidence location where available. Never invent missing prices, dates, SKUs, products, or mechanics. Invalid model items must be observable rather than silently disappearing. |
| `app/models/promotion.py` | **CHANGE** | Extend the observation/canonical model as needed for promotion identity, lifecycle, provenance, extraction metadata, and review state. Add database constraints/indexes through Alembic rather than ad-hoc runtime assumptions. |
| `app/services/crawler/base.py` | **CHANGE** | Remove insecure `verify=False` behavior for production. Add explicit timeout policy, retries/backoff, user-agent configuration, response/content-type metadata, content hashing, and deterministic document identity. |
| `app/services/crawler/superindo.py` | **CHANGE** | Move source URLs and crawl configuration into the source registry/configuration layer. Keep the adapter focused on source-specific parsing. Do not hardcode source discovery policy in the adapter. |
| `app/services/crawler/aggregator.py` | **CHANGE** | Replace broad selector-only discovery with source-aware adapters, pagination support, dynamic-content support, and document-type detection. Keep fallback extraction as a safety net, not the primary correctness mechanism. |
| Pipeline/orchestration service | **CHANGE** | Remove the current small hardcoded document/card limits. Add chunking, queueable jobs, retries, idempotency, job status, failure/dead-letter handling, and resumability. The exact existing pipeline filename must be confirmed before editing; do not invent a path. |
| `app/services/ranking/scorer.py` | **CHANGE** | Make ranking explainable. Separate commercial impact/relevance from data quality/confidence so uncertain observations do not receive an unjustified ranking advantage. Persist score components where useful for auditability. |
| API promotion routes | **CHANGE** | Keep `/promotions/top10`, but add canonical promotion detail/listing and statistics endpoints. Apply filtering/ranking in PostgreSQL where practical. Expose evidence and verification state. |
| Source API/routes | **ADD/CHANGE** | Expose source registry status, crawl health, and source metadata without exposing credentials. |
| Review queue API/routes | **ADD/CHANGE** | Support unresolved entities, low-confidence extraction, conflicting observations, and lifecycle anomalies as explicit review cases. |
| Scheduler | **CHANGE** | Schedule source-specific collection according to source frequency/priority. Prevent duplicate concurrent jobs and record job outcomes. |
| Pydantic schemas | **CHANGE** | Align request/response models with canonical promotion, observation, evidence, review, and confidence semantics. Do not expose internal ORM implementation details as the public contract. |
| Alembic migrations | **ADD** | Add the schema changes below as normal sequential Alembic revisions. Do not invent or depend on a specific migration filename until the actual migration tree is inspected. |
| Tests | **ADD/CHANGE** | Add unit, integration, database, crawler, extraction, entity-resolution, deduplication, API, and idempotency tests. |

## Promotion identity and deduplication rules

The canonical promotion must have a stable identity derived from source observations. The identity should use the strongest available commercial attributes, for example:

- retailer/source channel;
- resolved competitor/brand/product/SKU;
- normalized pack size where relevant;
- promotion type/mechanic;
- buy/get/bundle/voucher/cashback parameters;
- promotional price or other material commercial value;
- promotion title/offer identifier where reliably supplied by the source;
- effective date window when it is part of the source-defined offer identity.

Do not use raw text alone as identity. Do not use product + retailer + promotion type as identity. Do not merge two offers merely because they appear on the same page.

When identity is uncertain, retain separate observations and create a review case rather than performing an irreversible merge.

## Entity resolution rules

Resolution must follow this order:

1. Exact canonical identifier when available.
2. Exact normalized name/alias.
3. High-confidence deterministic alias mapping.
4. Candidate generation using safe fuzzy matching.
5. Candidate scoring using multiple attributes.
6. Automatic resolution only above a documented confidence threshold and without material ambiguity.
7. Otherwise mark unresolved and send to review.

New entities must not be created automatically from low-confidence text. Entity creation is a controlled operation and must remain auditable.

## Validation and lifecycle

Validation answers: **Is the extracted data internally valid?**

Lifecycle answers: **Is the promotion active, upcoming, expired, or otherwise not currently applicable?**

These concerns must remain separate.

Minimum lifecycle semantics:

- `UPCOMING`: source provides a future start date and the offer has not started.
- `ACTIVE`: evidence supports that the offer is currently active.
- `EXPIRED`: the known end date has passed.
- `UNKNOWN`: dates are missing/uncertain and active state cannot safely be determined.
- `INVALID`: the observation fails material data validation.
- `REVIEW`: the data may be usable but requires human verification because of ambiguity/conflict/low confidence.

The exact enum values may be adapted to the existing schema, but the semantics must remain explicit.

Missing dates must never be silently invented. A source that says an offer is available now without providing a date may justify an observation timestamp, but that timestamp is not automatically a promotion start date.

## Evidence integrity

Every canonical commercial claim must remain traceable to source evidence.

Required principles:

- Preserve source URL.
- Preserve crawl/document identity.
- Preserve observation identity.
- Preserve extraction timestamp.
- Preserve evidence text or source location where possible.
- Preserve page/image/PDF location when applicable.
- Never replace source evidence with model-generated wording as the only proof.
- If observations conflict, retain both and mark the conflict for resolution.

## LLM extraction contract

The extraction layer is responsible for converting source content into structured observations, not for deciding business truth by itself.

The model must:

- return schema-valid structured data;
- quote or reference source evidence for material fields;
- use `null`/unknown for absent information;
- never infer a price or discount that is not supported by the source;
- never assume a year merely because the current year is known;
- distinguish explicit source dates from inferred dates;
- preserve uncertainty and confidence;
- identify the source document and extraction context.

Model confidence is not a substitute for evidence.

## Crawler and document-processing plan

### HTML

The crawler should record HTTP status, final URL, content type, retrieval timestamp, content hash, and raw content/document reference.

### JavaScript-heavy pages

Use Playwright or an equivalent browser adapter only where ordinary HTTP retrieval cannot obtain the relevant content. Browser execution should be source-specific and bounded by time/resource limits.

### PDF

Detect PDFs explicitly and process text extraction before OCR. Preserve page numbers and source document identity.

### Images/catalogs

Use OCR/vision processing when promotional facts are present primarily in images. Preserve image/page coordinates where practical so evidence can be reviewed.

### Failures

Crawl failures must be recorded as job/document failures with retry state. A failed source must not appear healthy merely because a previous crawl succeeded.

## Database migration plan

Implement these as incremental Alembic revisions after confirming the exact existing migration tree.

### Migration A — promotion identity and lifecycle

- Add stable promotion fingerprint/identity field as appropriate.
- Add uniqueness constraints only after validating existing duplicate data.
- Add explicit lifecycle/status semantics.
- Add observation-to-canonical-promotion linkage if not already sufficient.
- Add indexes for active/upcoming/expired queries and fingerprint lookup.

### Migration B — entity resolution

- Add entity alias storage if absent.
- Add resolution confidence/state.
- Add review linkage for ambiguous entities.
- Add uniqueness constraints for canonical names/identifiers where business-safe.
- Add appropriate normalized/fuzzy-search indexes.

### Migration C — extraction/document provenance

- Add extraction run/model/version metadata where absent.
- Add source content hash/document identity.
- Add evidence location/page/coordinate fields where applicable.
- Add idempotency keys for crawl/extraction operations where required.

### Migration D — integrity and performance

- Add foreign-key constraints where missing.
- Add check constraints for impossible commercial values where practical.
- Add indexes based on real API/query plans.
- Consider `pg_trgm` indexes for controlled candidate generation, not as a substitute for deterministic resolution.

No migration may introduce a foreign key to `dwh_prod` or another database.

## Pipeline idempotency requirements

A retry of the same source document must not create duplicate canonical promotions or duplicate observations unless the source content or extraction run is genuinely distinct and the schema explicitly models that distinction.

At minimum:

- crawl job identity must be deterministic enough to detect duplicate work;
- document content hash should identify unchanged content;
- extraction should be repeatable without multiplying canonical records;
- promotion upsert/deduplication must be transaction-safe;
- partial failures must be resumable;
- failed jobs must be visible and retryable.

## API target

The public application contract should evolve toward:

- `GET /promotions/top10` — current high-priority active promotions.
- `GET /promotions` — filtered/paginated canonical promotions.
- `GET /promotions/{id}` — complete promotion plus evidence and verification state.
- `GET /promotions/stats` — operational/commercial summary.
- `GET /sources` — source registry and health metadata.
- `GET /review-queue` — unresolved/ambiguous cases.

API responses must distinguish canonical facts from evidence and confidence metadata.

## Ranking rules

Ranking should remain explainable and should not become a black-box model requirement.

Suggested conceptual components:

- commercial promotion strength;
- business/category relevance;
- source reliability;
- freshness;
- competitor importance;
- evidence quality;
- extraction confidence.

The implementation should expose enough score components to explain why an item reached the Top 10. Low-quality evidence should be prevented from dominating the list merely because the model assigned a high confidence value.

## Test matrix

### Unit tests

- promotion fingerprint stability;
- distinct promotions do not merge;
- exact duplicate observations do merge/update correctly;
- entity normalization and aliases;
- ambiguous entity candidates go to review;
- invalid price/discount combinations are rejected;
- lifecycle transitions;
- ranking component calculations;
- malformed LLM output handling.

### Integration tests

- crawl -> document -> observation -> canonical promotion;
- repeat crawl is idempotent;
- conflicting observations remain traceable;
- entity review path works;
- evidence remains attached after canonical updates;
- API returns evidence and lifecycle state;
- PostgreSQL constraints behave as expected.

### Source adapter tests

Each production source adapter must have representative fixtures for:

- ordinary HTML;
- pagination;
- dynamic content where applicable;
- PDF/catalog;
- image-based promotion;
- no-promotion page;
- changed source layout;
- temporary HTTP failure.

## Acceptance criteria

Implementation is aligned when all of the following are true:

1. Two materially different promotions for the same product/retailer can coexist.
2. Reprocessing the same evidence does not create duplicate canonical promotions.
3. Weak entity matches are not silently promoted to canonical entities.
4. Missing or uncertain dates are represented explicitly rather than fabricated.
5. Every material promotion claim can be traced to source evidence.
6. LLM extraction does not depend on a hardcoded calendar year.
7. Crawler TLS verification is enabled for normal production traffic.
8. Dynamic, PDF, and image-based sources have a documented processing path.
9. Failed jobs are observable and retryable.
10. Ranking is explainable and confidence-aware.
11. API consumers can inspect canonical promotion details and evidence.
12. Tests cover deduplication, entity resolution, validation, lifecycle, extraction, and idempotency.
13. All application database connections target only the dedicated `competitor_intel` database.
14. No code, migration, test, or documentation introduces integration with `dwh_prod`.

## Explicit non-goals / DO NOT rules

- Do **not** connect the application to `dwh_prod`.
- Do **not** inspect, reuse, copy, or query DWH data to improve competitor intelligence.
- Do **not** add cross-database foreign keys.
- Do **not** invent promotional values when the source does not provide them.
- Do **not** silently create entities from weak fuzzy matches.
- Do **not** merge promotions solely by product, retailer, and promotion type.
- Do **not** treat an observation timestamp as a source-provided promotion start date.
- Do **not** use `verify=False` as the normal production crawler configuration.
- Do **not** make the pipeline depend on a tiny fixed number of documents/cards.
- Do **not** make LLM confidence the sole basis for commercial truth.
- Do **not** perform a full rewrite when an incremental correction is sufficient.

## Implementation sequence

### P0 — correctness

1. Promotion identity/deduplication rewrite.
2. Entity-resolution rewrite.
3. Lifecycle/status semantics.
4. Validation and evidence integrity.
5. Idempotent pipeline behavior.
6. Database migrations and regression tests.

### P1 — source coverage

1. Source registry-driven configuration.
2. Robust HTTP crawling.
3. Dynamic page processing.
4. PDF extraction.
5. OCR/image processing.
6. Source-specific adapters.

### P2 — intelligence

1. Strict structured extraction.
2. Extraction provenance and confidence.
3. Review workflow.
4. Explainable ranking.

### P3 — product

1. Promotion list/detail/stats APIs.
2. Source health API.
3. Review queue API.
4. Dashboard and alerts.

### P4 — production hardening

1. Integration/regression suite.
2. Health checks.
3. Structured logging/metrics.
4. Retry/dead-letter operations.
5. Docker Compose application deployment.
6. Performance/query-plan tuning based on real workload.

## Completion rule

After each implementation phase, update the relevant documentation if a design decision changes. `master` remains the authoritative branch. Code changes must be validated against the PRD, technical design, this implementation plan, and the database isolation rule before being considered complete.
