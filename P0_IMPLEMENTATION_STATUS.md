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
7. refreshes extracted payload/confidence when the same document is explicitly reprocessed.

Migration:

`migrations/versions/2026_09_05_2000-c4a81e6f2b73_observation_idempotency.py`

adds uniqueness for `(document_id, promotion_id)`, preventing duplicate observations for the same promotion within one source document.

### P0-E — Structured extraction hardening 🟡

The extraction layer has now been hardened in `app/services/extraction/llm_extractor.py`:

- removed the hardcoded 2026 year;
- supplies an explicit runtime `CURRENT_DATE` to the model;
- allows callers/tests to inject a deterministic date;
- preserves the existing `extract_from_text()` list-returning API;
- adds `extract_with_metadata()` for auditable parser results;
- records model, extraction timestamp, raw model response, parser status, accepted items, and rejected items in the returned result;
- distinguishes `SUCCESS`, `PARTIAL_SUCCESS`, `EMPTY_RESPONSE`, `INVALID_JSON`, `INVALID_SCHEMA`, and `ERROR`;
- invalid individual promotion items are rejected without silently discarding valid items;
- exact evidence quotes remain required.

The extraction schema now also enforces:

- supported promotion categories;
- supported promotion types;
- non-negative prices;
- 0–100 discount percentage;
- positive BUY/GET quantities;
- 0–1 confidence;
- non-empty product names and evidence quotes.

Regression coverage was added in `tests/unit/test_llm_extractor.py` for runtime date context, partial item rejection, and malformed JSON visibility.

**Remaining P0-E work:** connect extraction metadata into the persisted observation/provenance flow so model/parser status is not lost when the normal pipeline calls the legacy list-returning API.

## P0-F — Integration and end-to-end verification ⏳

Still required before declaring P0 complete:

- migration chain verification against a clean database;
- unit tests for canonical upsert and observation idempotency;
- integration test: crawl document → extraction → validation → resolution → upsert → evidence;
- duplicate/reprocessing test;
- ambiguous entity test;
- lifecycle test around date boundaries;
- collision analysis before any unique promotion fingerprint constraint;
- CI execution and failure review.

## Migration chain

```text
d7bd4ee90139  initial MVP
      ↓
9f2c1a7b4d61  promotion identity
      ↓
b7e41c2d8f90  entity resolution audit
      ↓
c4a81e6f2b73  observation idempotency
```

## Database safety rule

All P0 changes remain inside the `competitor_intel` PostgreSQL schema/database.

No code or migration may introduce a dependency on `dwh_prod`.

## Master branch rule

Before updating an existing GitHub file, fetch the current `master` version and use its current blob SHA. Do not reuse a stale SHA from an earlier tool result.

For new files, create them once. For subsequent changes, fetch → verify SHA → update → verify commit.
