# Implementation Gates

**Repository:** `kurnFR/competitor-intel`  
**Branch:** `master`  
**Updated:** 2026-09-24

This document is the execution gate for the implementation sequence:

```
Foundation
→ Source Registry / Discovery
→ Crawling
→ Extraction
→ Canonicalization
→ Geography / Pricing
→ Ranking
→ Review
→ API
→ UI
→ Operations
→ Hardening
→ Production readiness
```

## Current gate

**Phase 0/1 — Foundation + acquisition verification**

The code already contains substantial P0 correctness work and P1 crawler foundations. The immediate gate is now executable PostgreSQL verification rather than adding more business features on top of an unverified schema.

### Gate criteria

1. A fresh PostgreSQL database can run `alembic upgrade head`.
2. The required `competitor_intel` schema and core tables exist.
3. Required PostgreSQL extensions are available through the migration chain.
4. The complete migration chain can be downgraded to `base` and rebuilt to `head`.
5. Unit tests pass in the same environment.
6. No dependency on `dwh_prod` is introduced.
7. The crawl foundation remains bounded, rate-limited, retryable, and idempotent.
8. Dynamic/PDF/image support remains explicit about optional runtime dependencies.

### What is not yet verified

The repository code has **not** been successfully executed against a clean PostgreSQL `competitor_intel` database from this development environment. The GitHub workflow added in this phase provides the missing repeatable clean-PostgreSQL gate, but production readiness remains unclaimed until that gate actually passes.

## Phase 0/1 implementation gaps

These remain after the current foundation work:

- live retailer/source validation against real websites;
- Playwright Chromium installation where dynamic sources require it;
- Tesseract `ind` + `eng` language data where OCR is enabled;
- durable object storage for raw binary PDF/image payloads;
- stronger rendered/PDF/image provenance;
- additional source adapters beyond the current retailer foundation;
- distributed rate limiting when multiple hosts/processes are used;
- end-to-end crawl → acquisition → extraction → resolution → canonical upsert verification against PostgreSQL;
- representative-data collision analysis before any promotion fingerprint uniqueness constraint;
- CI execution results from the clean PostgreSQL workflow.

## Exit rule

Do not move to production-readiness claims merely because migrations or unit tests pass. Production readiness requires the later end-to-end, operational, security, performance, source reliability, and recovery gates to pass with evidence.
