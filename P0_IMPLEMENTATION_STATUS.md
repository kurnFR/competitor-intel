# P0 Implementation Status

**Repository:** `kurnFR/competitor-intel`  
**Branch:** `master`  
**Updated:** 2026-09-05

## Purpose

This file records what has actually been implemented on `master`, rather than what is only planned in the architecture documents.

## Completed in P0-A: Promotion identity foundation

### Database

Added migration:

`migrations/versions/2026_09_05_1900-9f2c1a7b4d61_promotion_identity.py`

Revision chain:

```text
d7bd4ee90139
    -> 9f2c1a7b4d61
```

The migration adds:

- `promotions.identity_fingerprint` — nullable SHA-256 identity fingerprint.
- `promotions.identity_version` — currently `v1`.
- index on `promotions.identity_fingerprint`.
- `promotion_observations.promotion_id` — nullable link to the canonical promotion.
- foreign key from observation to promotion with `ON DELETE SET NULL`.
- index on `promotion_observations.promotion_id`.

### Important safety decision

There is deliberately **no unique constraint** on `identity_fingerprint` yet.

Before uniqueness can be enforced, existing production/staging data must be scanned for collisions and the fingerprint strategy must be validated against legitimate recurring promotions.

### ORM

`app/models/promotion.py` now exposes:

- `Promotion.identity_fingerprint`
- `Promotion.identity_version`
- `Promotion.observations`
- `PromotionObservation.promotion_id`
- `PromotionObservation.promotion`

The canonical promotion remains separate from its observations and evidence.

### Identity service

Added:

`app/services/promotions/identity.py`

The service generates a deterministic SHA-256 fingerprint from normalized commercial identity fields.

It intentionally excludes volatile values such as:

- AI confidence
- ranking score
- source reliability
- observation timestamp
- long descriptions

It includes material promotion attributes such as:

- retailer / competitor / brand / product identifiers
- normalized product name
- SKU and pack size
- promotion mechanic
- buy/get/bundle quantities
- cashback/voucher/minimum purchase values
- promotional price and currency
- promotion title
- effective dates
- channel and geography

The fingerprint is an **identity aid**, not automatic proof that two observations are the same promotion. Entity resolution and ambiguity handling remain required.

### Regression tests

Added:

`tests/unit/test_promotion_identity.py`

Coverage includes:

- deterministic fingerprints;
- normalization of case/whitespace;
- material promotion changes producing different identities;
- volatile metadata not changing identity;
- identity-version presence.

## What P0-A does NOT yet do

The application does not yet automatically link every observation to a canonical promotion using the fingerprint.

That is intentional.

The next step is the **promotion matching/upsert service**, which must:

1. calculate the fingerprint;
2. look for candidate canonical promotions;
3. distinguish exact identity from ambiguous candidates;
4. create a new canonical promotion when appropriate;
5. link the observation to the selected canonical promotion;
6. update `last_seen_at` safely;
7. preserve all observations and evidence;
8. remain transaction-safe and idempotent.

No automatic merge should happen merely because the fingerprint is similar.

## Next P0 work

### P0-B — canonical promotion matching/upsert

Create a dedicated service around the new identity field. It must be tested against:

- same promotion, repeated crawl;
- same promotion, changed description;
- same promotion, changed AI confidence;
- different promotion type for the same product;
- different price/mechanic;
- different effective period;
- incomplete observation;
- ambiguous candidate set.

### P0-C — entity resolution

Confirm the actual current resolver implementation before changing it. Add controlled matching, aliases, confidence thresholds, and review handling.

### P0-D — lifecycle and validation

Separate data validity from promotion activity. Missing/uncertain dates must not be silently fabricated.

### P0-E — extraction and pipeline idempotency

Then strengthen structured extraction, retry behavior, and stage-level idempotency.

## Database safety rule

All P0 changes remain inside the `competitor_intel` PostgreSQL schema/database.

No code or migration may introduce a dependency on `dwh_prod`.

## Master branch rule

Before updating an existing GitHub file, fetch the current `master` version and use its current blob SHA. Do not reuse a stale SHA from an earlier tool result.

For new files, create them once. For subsequent changes, fetch -> verify SHA -> update -> verify commit.
