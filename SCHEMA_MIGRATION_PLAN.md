# PostgreSQL Schema & Migration Plan

## Purpose

This document is the database-specific execution contract for the P0 correctness work in `competitor-intel`.

It is derived from the current GitHub `master` migration and the requirements in:

- `FMCG Competitor Promotion.md`
- `TECHNICAL_DESIGN.md`
- `IMPLEMENTATION_ALIGNMENT.md`
- `IMPLEMENTATION_FILE_PLAN.md`

It describes the target database changes without pretending that the production database has already been migrated.

## Current Alembic baseline

The repository uses Alembic with:

```text
script_location = migrations
```

The current migration chain contains one initial revision:

```text
2026_09_02_1521-d7bd4ee90139_initial_mvp_schema.py
revision: d7bd4ee90139
down_revision: None
```

This is the baseline. Future schema work must be added as new Alembic revisions; the initial migration must not be rewritten after it has been applied to an environment.

## Current schema baseline

The initial revision creates the `competitor_intel` schema and these core tables:

```text
competitors
entity_mapping
retailers
review_queue
source_registry
brands
crawl_jobs
crawl_documents
products
promotion_observations
promotions
promotion_evidence
```

The baseline already provides foreign keys between canonical entities, crawl documents, observations, promotions, and evidence. It also provides indexes for common name, status, source, date, and ranking access paths.

## Critical baseline observations

### 1. `promotion_observations` is too thin for the target provenance model

Current columns include:

- `document_id`
- `raw_text`
- `extracted_json`
- `ai_confidence`
- `observed_at`
- `created_at`

The target model needs enough information to distinguish an extraction event from the canonical promotion and to support repeatable/idempotent processing.

### 2. `promotions` is missing a stable commercial identity

The current table stores many commercial attributes but has no deterministic promotion fingerprint/identity column and no uniqueness rule protecting canonical identity.

This is the database-level reason the current deduplicator must not be trusted to decide identity using application-side substring matching alone.

### 3. `entity_mapping` does not sufficiently model ambiguity

It currently stores one canonical entity ID, match method, and confidence. The target workflow needs an explicit way to represent unresolved/ambiguous matches and review state without silently creating canonical entities.

### 4. `crawl_documents` has content hashes but no complete processing lifecycle

The baseline has `content_hash`, `document_type`, timestamps, and content fields. The target pipeline needs explicit processing/extraction state and provenance sufficient for retries and resumability.

### 5. `review_queue` exists but is generic

This is useful and should be retained. It should become the common human-review mechanism for entity ambiguity, extraction conflicts, invalid/uncertain promotion data, and lifecycle anomalies.

## Migration strategy

Do not redesign the entire database.

Use additive, backward-compatible migrations first, then data cleanup/backfill, then constraints/indexes after existing data has been validated.

Recommended sequence:

```text
Current d7bd4ee90139
        |
        v
P0-A promotion identity/lifecycle
        |
        v
P0-B entity resolution/provenance
        |
        v
P0-C extraction/document processing state
        |
        v
P0-D integrity/indexes
```

The exact generated revision IDs and filenames must be created by Alembic and must reference the actual previous revision. Do not hardcode a guessed revision ID in documentation or code.

## P0-A — Promotion identity and lifecycle

### Add to `promotions`

Add fields as required by the final ORM contract, with the preferred conceptual fields:

```text
promotion_fingerprint / identity_key
lifecycle/status fields if current status semantics are insufficient
commercial/ranking component fields where needed for explainability
```

The identity field must be deterministic and normalized.

It should incorporate the strongest available commercial identity attributes, such as:

- retailer/source channel;
- resolved competitor/brand/product/SKU;
- pack size where material;
- promotion mechanism;
- buy/get/bundle parameters;
- voucher/cashback/minimum purchase conditions;
- promotional price or other material commercial value;
- reliable source promotion identifier/title;
- date window where the source defines it as part of the offer identity.

### Important constraint rule

Do **not** immediately create a unique constraint on the new fingerprint.

First:

1. populate fingerprints;
2. identify collisions;
3. review collisions;
4. correct the identity algorithm/data;
5. only then add a unique constraint if the business semantics prove that the fingerprint is truly canonical.

### Lifecycle

The database must distinguish at minimum:

```text
UPCOMING
ACTIVE
EXPIRED
UNKNOWN
INVALID
REVIEW
```

The implementation may use a different enum/string representation if it preserves these semantics.

## P0-B — Entity resolution and aliases

### `entity_mapping`

Extend the mapping model to support:

```text
resolution_status
resolved_at
review_queue_id or equivalent linkage
alias/normalized source value
```

The exact field names are implementation decisions, but the semantics are mandatory.

### Alias support

Add an alias structure if the existing application does not already provide one. It should support:

```text
entity_type
canonical_entity_id
alias_value
normalized_alias
source_id (nullable when global)
confidence / match method
created_at / updated_at
```

Use uniqueness constraints carefully so the same alias cannot accidentally resolve to two canonical entities in the same scope.

### Fuzzy search

If PostgreSQL `pg_trgm` is enabled, use it for candidate generation and search performance only. It must not become the sole truth mechanism for entity resolution.

## P0-C — Extraction and document processing provenance

### `crawl_documents`

Extend processing state as required:

```text
processing_status
processing_attempts
processed_at
processing_error
content_type / detected_type if not already represented
```

The system should be able to tell whether a document was:

```text
retrieved
queued
processing
processed
failed
skipped_unchanged
```

### `promotion_observations`

Extend provenance as required:

```text
extraction_run_id or equivalent
extractor/model identifier
prompt/schema version where useful
validation status
resolution status
idempotency key where required
```

Keep `extracted_json` as raw model-output/provenance storage where useful, but do not treat raw model JSON as the canonical business record.

## P0-D — Integrity and performance

After data is validated, add constraints/indexes for:

- promotion fingerprint lookup;
- active/status queries;
- lifecycle date queries;
- observation/document lookup;
- entity alias lookup;
- review queue state;
- source/document freshness;
- common API filters.

Use partial indexes where they materially improve active-promotion queries and PostgreSQL supports the required predicate.

Consider `pg_trgm` only if candidate search measurements justify it.

## Money and numeric correctness

The current baseline uses floating-point columns for prices, discounts, scores, and similar values.

For monetary values, the target implementation should prefer PostgreSQL `NUMERIC`/SQLAlchemy `Numeric` with an explicit precision/scale appropriate to the business domain.

Do not perform a blind type conversion in the first migration if existing data may be dirty. The migration must first assess the existing values and define a safe conversion strategy.

Percentage/ranking/confidence fields may remain numeric floating-point values where precision requirements are appropriate, but their valid ranges should be constrained where practical.

## Foreign-key and delete semantics

Retain the existing isolated schema and foreign-key structure.

Review `CASCADE` vs `SET NULL` behavior before adding new relationships. Historical competitor intelligence must not disappear merely because a canonical entity is later deactivated or corrected.

In particular:

- evidence should remain historically traceable;
- observations should remain auditable;
- canonical entity corrections should not erase historical source evidence;
- deleting a source configuration should not silently destroy the intelligence history unless that behavior is explicitly required.

## Data migration / backfill policy

Before applying any new uniqueness constraint or irreversible transformation:

1. snapshot/backup the target `competitor_intel` database;
2. run duplicate detection;
3. generate a collision report;
4. resolve or quarantine ambiguous records;
5. backfill deterministic fields;
6. validate row counts and foreign-key integrity;
7. only then add strict constraints.

Never use a destructive migration to hide duplicate or invalid records.

## Isolation requirement

This database remains completely independent from the production DWH.

The application must connect only to the dedicated `competitor_intel` database/schema.

No migration may:

- create a foreign key to `dwh_prod`;
- create a database link to `dwh_prod`;
- query DWH tables;
- copy DWH data into competitor intelligence;
- depend on DWH schema objects.

## Migration acceptance tests

Every P0 migration must be tested in a clean PostgreSQL database and against a representative copy of the current `competitor_intel` data.

Required checks:

```text
alembic upgrade head
alembic downgrade <previous revision>
alembic upgrade head
```

plus:

- schema exists;
- all expected tables exist;
- foreign keys are valid;
- indexes exist;
- existing rows remain accessible;
- fingerprints are deterministic;
- duplicate collisions are reported rather than silently merged;
- historical evidence remains accessible;
- API queries still work;
- no DWH connection is required.

## Definition of database done

The database portion of P0 is complete only when:

1. A canonical promotion has a deterministic identity.
2. Distinct commercial offers cannot be accidentally merged by a weak identity rule.
3. Repeat processing can be represented idempotently.
4. Entity ambiguity can be persisted and reviewed.
5. Document/extraction processing state is observable.
6. Lifecycle state is explicit.
7. Evidence remains traceable.
8. Money fields have an agreed numeric representation.
9. Constraints are applied only after duplicate/backfill validation.
10. All migrations are reversible where safely possible.
11. The migration chain remains linear from `d7bd4ee90139`.
12. No `dwh_prod` dependency exists.
