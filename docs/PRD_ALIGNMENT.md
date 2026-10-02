# PRD alignment

Status of the product requirements (`FMCG Competitor Promotion.md`, PRD sections 1-21) against what is built.
**Done** = implemented and covered by automated tests. **Partial** = some of it. **Not built** = not started.
Nothing here has been proven against your real sources yet (PRD section 20 success criteria need a real crawl).

| PRD | Requirement | Status | Notes |
|---|---|---|---|
| 5 | Public collection only; obey restrictions; **a failed crawl is never "zero promotions"** | Done | robots.txt honoured. A promotion is only marked `NOT_LISTED` when its source was successfully *collected and processed* later and no longer lists it. Failed crawls/extractions are recorded on the source. Partial: no explicit "blocked" status yet (a robots refusal shows as a failing source). |
| 6 | Source registry: type, reliability, adapter, frequency, health, active; approval lifecycle; disable without deleting history | Done | Sources are added as **candidates** and never crawled until approved with an explicit adapter. Domains are never sniffed to guess a parser. Rejected/paused sources are never crawled. |
| 6 | **Source discovery** (find new sources automatically) | Not built | Sources are added by an administrator by hand. |
| 6 | **URL registry** (per-URL schedule, content hash, next crawl) | Partial | Scheduling is per *source* (each has its own frequency; the scheduler runs only what is due). Per-URL targets are not modelled. Unchanged pages are detected by content hash. |
| 7-8 | Core data model and promotion fields | Partial | Promotion, observation, evidence, change events, review queue, entities exist. The separate geography tables of the PRD are not modelled (see 9). |
| 9 | Geography first-class: keep source wording, normalise separately, **never assume nationwide** | Done (macro-region level) | Wording is extracted verbatim and **dropped if it does not appear in the page**; mapped to Jawa / Sumatera / Kalimantan / Sulawesi / Bali-Nusra / Maluku / Papua / Jabodetabek / Online / Selected stores / Nationwide(stated) / Several / Unmapped / **Not stated**. Province, city and store level are kept only as wording. *Previously every promotion was silently labelled "Indonesia"; that is fixed and existing rows are reset to Not stated.* |
| 10 | **Regional pricing** kept visible per region | Done | `/regional`: one row per product, one column per region; "Not stated" is its own column, never merged. |
| 11 | Evidence and provenance | Done | Verbatim evidence quote required; source URL, document and observation kept. |
| 12-13 | AI extraction and validation/quality gate | Done | Quote must appear in the page; prices/discounts/dates validated; rejected items counted. Quality still needs measuring on real pages (`scripts/eval_extraction.py`). |
| 14 | **Top 10 eligibility** | Done except contradictions | Requires: commercially active, `last_verified_at` within the window (default 90 days), evidence exists, source approved + active, identity resolved (competitor or brand linked). Optional strict geography gate (see decisions). **Not built:** "no material unresolved contradiction" (needs section 16). |
| 14 | Explainable Impact Score | Partial | Score combines strength, discount, source reliability, freshness, importance and change impact; the breakdown is not shown in the UI. |
| 15 | Freshness vs validity | Done | `last_seen_at` (observed), `last_verified_at` (validated), source `last_success_at` / `last_processed_at` (collected / processed), `start_date`/`end_date` (validity). An explicit past end date overrides freshness. |
| 16 | **Multi-source conflict** handling | Not built | Different sources reporting different prices are treated as changes to one promotion; there is no cross-source conflict detection or review. |
| 17 | UX: Overview, Promotions, Regional Pricing, Competitors, Sources, Review Queue, Settings | Partial | Dashboard (Overview + Promotions + evidence drawer), Regional pricing, Review queue, Insights (competitor activity), Price comparison, Admin (sources + health, users, scan history, security log), Account. **Missing:** a dedicated Competitors page and a read-only Sources/health view for non-admins. |
| 18 | Scan now vs Discover | Partial | "Scan now" crawls all approved, active sources. Discover is not built. |
| 19 | PostgreSQL boundary; UI reads production data only | Done | No mock/fallback rows in the UI. |
| 20 | Success criteria on a real source | **Not verified** | Needs a real scan with your LLM. |

## Decisions for you

1. **PR #1 (`docs/production-architecture-v2`).** It cannot merge: it is a parallel code line with a different migration chain
   (15 files conflict, and it deletes the original initial migration). The requirement documents in it are valuable; the code overlaps with
   what is now in `master` (source approval/adapters, URL validation, geography). Recommended: close PR #1 and, if you want the
   documents in the repo, add them in a docs-only PR rebased on `master`.
2. **"Geography sufficiently understood" (PRD 14).** Read strictly it would hide every promotion whose page states no region, which
   is most catalog pages. Default here: show them, labelled "Not stated". Set `TOP10_REQUIRE_KNOWN_GEOGRAPHY=true` for the strict reading.
3. **Identity gate.** Promotions with no competitor or brand linked are hidden until someone resolves them on the Review page
   (`TOP10_REQUIRE_RESOLVED_IDENTITY=false` turns this off). Items with no suggested match can only be rejected today, so check the
   Review page after the first real scan.
4. **How long an undated promotion survives** after its source stops listing it: `UNDATED_PROMO_MAX_AGE_DAYS` (default 14).
5. **Approval.** The same administrator can add and approve a source. Say so if you want a two-person rule.

## Not built yet (suggested order)

1. Multi-source conflict detection and review (PRD 16), then the "no unresolved contradiction" Top 10 gate.
2. Source discovery (PRD 6/18) with a candidate queue.
3. Per-URL registry and schedules.
4. Province/city/store-level geography as structured data.
5. Competitors page, read-only source health for analysts, explainable score breakdown.
