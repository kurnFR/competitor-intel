# IMPLEMENTATION_AUDIT.md — Implementation Status Against the Production Plan

> **Planning baseline:** `IMPLEMENTATION_PLAN.md` is the master execution plan. This audit records implementation reality against that plan.
>
> **Current status (2026-09-25):** implementation remains **NOT PRODUCTION READY**. The repository is a partial vertical slice and must pass the phase exit gates before production source expansion.

## Current phase status

| Phase | Status | Notes |
|---|---|---|
| 0 Foundation | PARTIAL | Bootstrap explicitly creates/drops the application schema; clean PostgreSQL migration/test execution still required. |
| 1 Discovery & Registry | PARTIAL | Discovery, lifecycle transitions, URL registration/disablement, SSRF validation and admin authorization are implemented; full integration/assessment verification remains. |
| 2 Crawling & Change Detection | PARTIAL | Due-target selection, explicit adapters, change detection, backoff and redirect validation exist; scheduler/fixture/operational verification remains. |
| 3 Extraction & Validation | PARTIAL | AI schema and deterministic validation foundations exist; source-specific fixture coverage remains. |
| 4 Observation & Canonicalization | PARTIAL | Observation/evidence/dedup foundations exist; full material identity/conflict test coverage remains. |
| 5 Geography & Regional Pricing | PARTIAL | Relational geography and regional price observations exist; normalization and regression coverage remain. |
| 6 Ranking / Top 10 | PARTIAL | Eligibility/freshness/evidence/source gates exist; explainable scoring and full regression coverage remain. |
| 7 Review Workflow | PARTIAL | Review decision/audit path exists; end-to-end review UI/API verification remains. |
| 8 API Contracts | PARTIAL | Core endpoints exist; contract tests and stable error/filter/pagination semantics remain. |
| 9 Dashboard / UI | PARTIAL | API-backed UI foundation exists; production UX hardening and E2E verification remain. |
| 10 Production Operations | NOT COMPLETE | Scheduler, monitoring, alerts, backups and adaptive operations remain. |
| 11 Testing & Hardening | NOT COMPLETE | Clean-DB integration, source fixtures, E2E, security and reliability suites remain. |
| 12 Production Readiness | NOT COMPLETE | Final deployment, recovery and acceptance gates remain. |

## Latest hardening completed

- Fixed the bootstrap migration so `competitor_intel` is created before SQLAlchemy metadata creation.
- Cleaned the review/price migration and made its downgrade tolerant of already-absent objects.
- Changed crawler orchestration to select sources only when an approved active registered URL is due.
- Added source discovery/lifecycle endpoints with explicit adapter-gated activation and independent URL disablement.
- Added public HTTP(S) URL validation that rejects credential-bearing and private/local/reserved targets.
- Added crawl-time DNS and redirect validation to reduce SSRF risk.
- Added source lifecycle transition unit tests.
- Added an explicit administrative token requirement for source mutations and manual pipeline execution.
- Restricted CORS configuration to explicit configured origins instead of wildcard access.
- Preserved explicit adapter selection; unsupported sources still fail rather than using a generic parser.

## Immediate implementation order

1. Verify and harden the migration chain against a clean `competitor_intel` database.
2. Complete Phase 1 source discovery/assessment and registry contracts.
3. Complete Phase 2 due-target scheduling, browser fallback verification, backoff and change detection.
4. Complete Phase 3 source fixtures and deterministic validation.
5. Complete Phase 4 material deduplication and conflict handling.
6. Complete Phase 5 geography normalization and regional pricing.
7. Complete Phase 6 explainable Top 10 scoring.
8. Complete Phase 7 review workflow.
9. Stabilize Phase 8 API contracts.
10. Harden Phase 9 UI.
11. Build Phase 10 operations.
12. Execute Phase 11 hardening.
13. Execute Phase 12 production acceptance.

## Important verification status

The current development environment has **not successfully executed the complete test suite against a clean PostgreSQL `competitor_intel` database**. Do not treat existing test files as proof of production readiness.

Before any production claim, run:

```bash
alembic upgrade head
pytest
```

against a clean PostgreSQL database configured for this application, plus the source-fixture, integration and E2E suites defined in `IMPLEMENTATION_PLAN.md`.

## Architecture invariants

These remain non-negotiable:

- PostgreSQL `competitor_intel` is the UI source of truth.
- `dwh_prod` is out of scope.
- Normal scheduled crawling uses approved registered URL targets.
- Discovery is separate from production crawling.
- Unsupported/unapproved sources are not silently crawled.
- No authentication/CAPTCHA/paywall/private-access bypass.
- Failed crawl is not interpreted as zero promotions.
- Observations remain immutable.
- Evidence is required for verified commercial facts.
- Unknown geography remains unknown.
- Regional/channel/material commercial differences are not silently merged.
- Explicit expiry overrides crawl freshness.
- Top 10 uses `last_verified_at`, not merely `last_seen_at`.
- UI contains no synthetic production promotion rows.
- Administrative mutations require configured authorization.
- Production behavior changes require documentation, migration where applicable, and tests.

## Source of truth for execution

See `IMPLEMENTATION_PLAN.md` for phase objectives, dependencies, exit gates and production acceptance criteria.
