# P0 Implementation Status

**Repository:** `kurnFR/competitor-intel`  
**Branch:** `master`  
**Updated:** 2026-09-06

## Purpose

This file records what has actually been implemented on `master`, rather than what is only planned in the architecture documents.

## Completed P0 work

### P0-A — Promotion identity foundation ✅

Added deterministic promotion identity with a legacy v1 fingerprint and a stable v2 source-observed commercial fingerprint. The v2 identity is independent of mutable canonical entity UUIDs and marketing copy/date changes, while preserving retailer/channel/geography boundaries. `promotions.source_identity_fingerprint` is indexed and intentionally not unique until real-data collision analysis is complete.

### P0-B — Entity resolution ✅

The resolver avoids silent entity creation and weak fuzzy matches. Outcomes are `RESOLVED`, `REVIEW`, or `UNRESOLVED`. Resolution audit persistence and migration retain source values, candidate IDs, confidence, and review status. Regression coverage is in `tests/unit/test_entity_resolution.py`.

### P0-B1 — Product entity resolution ✅

`app/services/entity_resolution/product.py` now resolves products within a resolved brand boundary using barcode, SKU, normalized name, and conservative `pg_trgm` fuzzy matching. Strong fuzzy matches require both a high similarity threshold and a dominance margin. Explicit pack-size conflicts go to review rather than silently selecting another SKU. The main pipeline persists product IDs when resolved and creates PRODUCT review items otherwise. Regression coverage is in `tests/unit/test_product_resolution.py`.

### P0-C — Validation and lifecycle ✅

`app/services/validation/validator.py` validates core promotion fields, supported mechanics, dates, price relationships, and BUY_X_GET_Y quantities. `app/services/validation/lifecycle.py` separates validity from activity state: `ACTIVE`, `UPCOMING`, `EXPIRED`, `UNKNOWN`. Missing dates are not fabricated from crawl time.

### P0-D — Canonical promotion upsert and observation idempotency ✅

`app/services/promotions/upsert.py` builds identity, first checks the legacy identity, then the stable source identity, finds/creates the canonical promotion, updates canonical attributes, links observations, persists exact evidence quotes, and avoids duplicate evidence. Migration `2026_09_05_2000-c4a81e6f2b73_observation_idempotency.py` adds uniqueness for `(document_id, promotion_id)`.

### P0-E — Structured extraction and provenance hardening ✅

`app/services/extraction/llm_extractor.py` uses runtime `CURRENT_DATE`, supports richer parser metadata, preserves valid items when individual items fail validation, and distinguishes parser outcomes. Exact evidence quotes remain required. Observation provenance records model, status, extraction timestamp, raw-response hash, and rejected count. Regression coverage is in `tests/unit/test_llm_extractor.py`.

### P0-F — Pipeline integration and idempotency wiring ✅

`scripts/run_pipeline.py` uses the richer extraction result, hashes the raw model response, resolves entities conservatively, resolves products within the canonical brand boundary, validates/canonicalizes through the shared upsert path, persists evidence and entity review items, and commits per document. The main path no longer manually inserts observations before deduplication or routes through the legacy promotion deduplicator.

### P0-G — Change-aware marketing ranking ✅

`app/services/promotions/change_detection.py` detects material price/value, mechanic, date, and terms changes before canonical refresh. `PromotionScorer.calculate_change_impact()` converts those changes into a bounded ranking signal, and the canonical upsert feeds that signal into `rank_score`. The ranking remains dominated by promotion strength while giving material changes enough weight to surface above otherwise similar stale promotions. Missing source fields still do not erase known canonical values, including a previously known discount. Regression coverage is in `tests/unit/test_promotion_scoring.py` and `tests/unit/test_promotion_upsert.py`.

## P1 work started — crawler reliability and acquisition foundation 🟡

`app/services/crawler/base.py` has TLS verification, bounded transient retries, URL canonicalization, duplicate-document detection, source status timestamps, durable initial retry state, per-source rate limiting, and a new binary-content fetch path.

### P1 — Durable retry/resume state 🟢

Migration `migrations/versions/2026_09_05_2100-f6a91c3d8e52_crawl_job_retry_state.py` adds retry scheduling, retry budget, last-attempt and worker fields plus a queue index. `job_queue.py` owns validated state transitions and PostgreSQL `FOR UPDATE SKIP LOCKED` claiming. `job_worker.py` provides bounded processing with per-job transaction boundaries. `job_processor.py` bridges persisted jobs to source adapters. `scripts/run_crawl_worker.py` provides a bounded worker entrypoint. Regression coverage is in `tests/unit/test_crawler_job_queue.py` and `tests/unit/test_crawler_job_worker.py`.

### P1 — Source rate limiting and concurrency 🟢

`app/services/crawler/rate_limiter.py` provides a thread-safe process-wide per-source limiter with configurable requests/second and maximum concurrency. `BaseCrawler.fetch_url()` applies it to every request, including retries. The conservative default is 1 request/second and 1 concurrent request per source.

### P1 — PDF/image and dynamic-page acquisition 🟢 foundation

`app/services/crawler/content.py` adds deterministic document-type detection from MIME type, URL extension, and magic bytes; PDF text extraction through `pypdf`; image OCR through optional Pillow + Tesseract; and a Playwright-based optional dynamic-page renderer. Dynamic rendering is only attempted for pages whose static content looks JS-driven or yields insufficient text. Missing optional browser/OCR capabilities produce explicit errors instead of silently inventing content.

### P1 — Bounded deep pagination/discovery 🟢

`app/services/crawler/discovery.py` provides conservative same-origin pagination discovery with a hard page budget, promotion-relevant path filtering, fragment removal, deterministic ordering, and duplicate suppression. `AggregatorCrawler` now expands from configured seed URLs instead of stopping at hardcoded page 1/page 2. Dynamic rendering is also applied before pagination discovery when a seed page is detected as JavaScript-driven.

The discovery budget is currently **10 pages per aggregator crawl** to prevent accidental whole-site crawling. Regression coverage is in `tests/unit/test_discovery.py`.

### P1 — Retailer-specific promotion adapters 🟢 foundation

`app/services/crawler/retailer.py` adds a source-specific promotion discovery adapter for **Indomaret** and **Alfamart**. `manager.py` dispatches those domains to the adapter rather than the generic aggregator. The adapter keeps a bounded 10-page crawl, follows same-retailer promotion/catalog links, handles `www`/apex host variants, reuses the existing rate-limited fetch path, and routes PDF/image assets through the existing acquisition layer. Regression coverage is in `tests/unit/test_retailer_crawler.py`.

This is intentionally a discovery/extraction foundation, not a claim that retailer-specific live URLs or anti-bot behavior have been fully validated in production.

## Remaining P1 work

- install/operate Playwright Chromium where dynamic rendering is enabled;
- install/configure Tesseract language data (`ind` + `eng`) where image OCR is enabled;
- durable raw PDF/image object storage instead of encoding binary payloads into the legacy text field;
- deepen retailer-specific adapters with validated live source paths and retailer-specific selectors/API endpoints;
- add adapters for the next priority sources (Superindo, Hypermart, Lotte, Yogya, TIP TOP, Transmart, and major marketplace/brand sources);
- stronger document provenance for rendered/PDF/image sources;
- distributed rate limiting if workers are deployed across multiple processes/hosts.

## Remaining verification before declaring P0 production-ready ⏳

- run the complete unit-test suite in the repository environment;
- verify the full Alembic migration chain against a clean `competitor_intel` database;
- run crawl → acquisition → extraction → validation → resolution → upsert → evidence integration;
- verify duplicate/reprocessing behavior against PostgreSQL constraints;
- test ambiguous/unresolved entity cases with persisted audit records;
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
      ↓
91c4e7a2b5d8  raw document provenance
      ↓
4c8d2e7f1a63  stable promotion source identity
```

## Database safety rule

All P0/P1 changes remain inside the `competitor_intel` PostgreSQL schema/database. No code or migration may introduce a dependency on `dwh_prod`.

## Master branch rule

All implementation updates in this workflow are committed directly to `master`. Before updating an existing GitHub file, fetch the current `master` version and use its current blob SHA. Do not reuse a stale SHA from an earlier tool result.
