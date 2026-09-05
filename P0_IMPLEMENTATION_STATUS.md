# P0 Implementation Status

**Repository:** `kurnFR/competitor-intel`  
**Branch:** `master`  
**Updated:** 2026-09-05

## Purpose

This file records what has actually been implemented on `master`, rather than what is only planned in the architecture documents.

## Completed P0 work

### P0-A — Promotion identity foundation ✅

Added migration:

`migrations/versions/2026_09_05_1900-9f2c1a7b4d61_promotion_identity.py`

The migration adds `promotions.identity_fingerprint`, `identity_version`, an identity index, and the observation-to-promotion link.

The identity service generates a deterministic SHA-256 fingerprint from normalized commercial identity fields while excluding volatile values such as AI confidence, ranking score, source reliability, and observation timestamps.

There is deliberately **no unique constraint** on the fingerprint yet. Existing data must be checked for collisions before uniqueness is enforced.

Regression coverage is in `tests/unit/test_promotion_identity.py`.

### P0-B — Entity resolution ✅

The resolver was hardened to avoid silent entity creation and weak fuzzy matches.

Resolution outcomes now distinguish:

- `RESOLVED` — exact/known alias or sufficiently dominant high-confidence match;
- `REVIEW` — ambiguous or weak candidate;
- `UNRESOLVED` — no acceptable candidate.

Resolution audit persistence and migration were added so source values, candidate IDs, confidence, and review status can be retained.

Regression coverage is in `tests/unit/test_entity_resolution.py`.

### P0-C — Validation and lifecycle ✅

`app/services/validation/validator.py` validates core promotion fields, supported mechanics, dates, price relationships, and BUY_X_GET_Y quantities.

`app/services/validation/lifecycle.py` separates promotion validity from activity state:

- `ACTIVE`
- `UPCOMING`
- `EXPIRED`
- `UNKNOWN`

Missing dates are not fabricated from crawl time.

### P0-D — Canonical promotion upsert and observation idempotency ✅

Added `app/services/promotions/upsert.py`.

The service:

1. builds the promotion identity payload;
2. calculates the fingerprint;
3. finds or creates the canonical promotion;
4. updates canonical non-null attributes;
5. links the observation to the canonical promotion;
6. preserves the original observation timestamp on reprocessing;
7. refreshes extracted payload/confidence when the same document is explicitly reprocessed;
8. persists the extractor's exact `evidence_quote` as `PromotionEvidence`;
9. avoids duplicate evidence when the same promotion/document/quote is reprocessed.

Migration:

`migrations/versions/2026_09_05_2000-c4a81e6f2b73_observation_idempotency.py`

adds uniqueness for `(document_id, promotion_id)`, preventing duplicate observations for the same promotion within one source document.

### P0-E — Structured extraction hardening ✅

The extraction layer has been hardened in `app/services/extraction/llm_extractor.py`:

- removed the hardcoded 2026 year;
- supplies an explicit runtime `CURRENT_DATE` to the model;
- allows callers/tests to inject a deterministic date;
- preserves the existing `extract_from_text()` list-returning API;
- adds `extract_with_metadata()` for auditable parser results;
- records model, extraction timestamp, raw model response, parser status, accepted items, and rejected items in the returned result;
- distinguishes `SUCCESS`, `PARTIAL_SUCCESS`, `EMPTY_RESPONSE`, `INVALID_JSON`, `INVALID_SCHEMA`, and `ERROR`;
- invalid individual promotion items are rejected without silently discarding valid items;
- exact evidence quotes remain required;
- canonical upsert persists each accepted item's exact evidence quote into `promotion_evidence`.

The extraction schema enforces:

- supported promotion categories;
- supported promotion types;
- non-negative prices;
- 0–100 discount percentage;
- positive BUY/GET quantities;
- 0–1 confidence;
- non-empty product names and evidence quotes.

Regression coverage is in `tests/unit/test_llm_extractor.py`.

### P0-F — Pipeline integration and idempotency wiring ✅

`scripts/run_pipeline.py` now uses the richer extraction result and passes extraction provenance into the canonical promotion upsert path.

The pipeline now:

1. crawls fresh sources or loads the latest documents;
2. processes bounded text blocks;
3. extracts structured promotions with parser metadata;
4. hashes the raw model response without persisting the full raw response in the observation row;
5. resolves retailer and brand/competitor conservatively;
6. validates and canonicalizes promotions through the shared upsert service;
7. persists promotion evidence;
8. commits per document.

The main pipeline no longer manually inserts `PromotionObservation` before deduplication and no longer routes the main path through the legacy promotion deduplicator.

A regression test was added in `tests/unit/test_promotion_upsert.py` for same-document reprocessing: one canonical promotion, one observation, and one evidence row are retained while extraction provenance is refreshed.

## P1 work started — crawler reliability foundation 🟡

`app/services/crawler/base.py` has been hardened and committed directly to `master`.

Current improvements:

- TLS certificate verification is enabled;
- transient HTTP statuses (`408`, `425`, `429`, `500`, `502`, `503`, `504`) are retried;
- bounded exponential backoff is used;
- `httpx.HTTPError` failures are retried within the configured limit;
- URLs are canonicalized by scheme/host/path/query with fragments removed;
- crawl jobs are retained even when the document content is a duplicate;
- duplicate successful documents are skipped using source + canonical URL + content hash;
- source success/error timestamps are updated;
- crawler regression coverage exists in `tests/unit/test_crawler_base.py` for URL canonicalization, hashing, transient-status retry, connection-error retry, and non-transient status handling.

### P1 — Durable retry/resume state 🟡

A durable queue state layer has now been added without coupling source-specific crawling to queue mechanics.

Migration:

`migrations/versions/2026_09_05_2100-f6a91c3d8e52_crawl_job_retry_state.py`

adds `next_retry_at`, `max_retries`, `last_attempt_at`, and `worker_id` to `crawl_jobs`, plus an index for retry-queue polling.

`app/services/crawler/job_queue.py` now owns deterministic transitions:

```text
QUEUED → RUNNING → SUCCESS
             ↓
         RETRY_WAIT → RUNNING
             ↓
        DEAD_LETTER
```

It provides bounded exponential backoff, explicit transition validation, retry-budget enforcement, and PostgreSQL `FOR UPDATE SKIP LOCKED` job claiming so multiple workers can safely poll the same queue.

`app/services/crawler/job_worker.py` provides a bounded worker loop with per-job transaction boundaries. Processor exceptions are persisted as retry state and eventually dead-lettered instead of terminating the whole batch.

Regression coverage was added in:

- `tests/unit/test_crawler_job_queue.py`
- `tests/unit/test_crawler_job_worker.py`

This is now a reusable durable queue foundation. Source-specific resumable processing still needs to be wired into the worker, and rate limiting, dynamic-page handling, PDF/image acquisition, OCR, deeper discovery/pagination, and source-specific adapters remain P1 work.

## Remaining verification before declaring P0 production-ready ⏳

- run the complete unit-test suite in the repository environment;
- verify the full Alembic migration chain against a clean `competitor_intel` database;
- run the crawl → extraction → validation → resolution → upsert → evidence integration path;
- verify duplicate/reprocessing behavior against PostgreSQL constraints;
- test ambiguous and unresolved entity cases with persisted audit records;
- test lifecycle boundaries around start/end dates;
- analyze existing promotion fingerprint collisions before adding a unique fingerprint constraint;
- review CI execution and failures once CI is available/confirmed.

## Migration chain

```text
d7bd4ee90139  initial MVP
      ↓
9f2c1a7b4d61  promotion identity
      ↓
b7e41c2d8f90  entity resolution audit
      ↓
c4a81e6f2b73  observation idempotency
      ↓
e5d72a1c9b40  extraction provenance
      ↓
f6a91c3d8e52  crawl job retry state
```

## Database safety rule

All P0/P1 changes remain inside the `competitor_intel` PostgreSQL schema/database.

No code or migration may introduce a dependency on `dwh_prod`.

## Master branch rule

All implementation updates in this workflow are committed directly to `master`.

Before updating an existing GitHub file, fetch the current `master` version and use its current blob SHA. Do not reuse a stale SHA from an earlier tool result.

For new files, create them once. For subsequent changes, fetch → verify SHA → update → verify commit.
