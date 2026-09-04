# PRD.md — FMCG Competitor Promotion Intelligence

## 1. Product Vision

Build an AI-powered competitive promotion intelligence platform for the Indonesian FMCG snack market, initially focused on biscuits, crackers, cookies and wafers.

The platform continuously discovers and monitors relevant public sources, converts source content into structured commercial observations, validates facts against evidence, resolves products/brands/competitors, preserves geographic scope, and presents important active activities to marketing, trade marketing, sales and management.

The system is a **decision-support product**. It must prefer an explicit unknown value over an invented value.

## 2. Primary Business Question

> What are the 10 most commercially important competitor promotions that are active now, recently verified, geographically understood, and supported by reliable evidence?

A promotion is not trustworthy unless the user can trace it to source evidence.

## 3. Business Outcomes

The platform should reduce manual competitor monitoring and enable users to understand:

- competitor/brand activity
- exact product/SKU/pack size
- promotion mechanic
- regular vs promotional price
- effective discount when calculable
- retailer/channel
- geographic validity
- start/end validity
- source reliability
- last verification
- why an activity ranks highly
- regional price and promotion differences

## 4. Scope

### 4.1 Market

Indonesia.

### 4.2 Categories

- Biscuit
- Cracker
- Cookie
- Wafer
- Sandwich biscuit
- Cream biscuit
- Sweet biscuit
- Savory cracker
- closely related snack products only when relevant

### 4.3 Multi-Source Strategy

The system must **not depend on one source**. Hemat.id is an initial source only.

Candidate source classes include:

- official manufacturer/company websites
- official brand websites and campaign pages
- official retailer websites/catalogs
- modern trade such as Superindo, Alfamart, Indomaret, Hypermart and local modern trade
- convenience retail pages/apps where public access is permitted
- verified marketplace stores
- public e-commerce pages such as Tokopedia, Shopee and TikTok Shop where collection is permitted
- established news/media
- promotion/price aggregation sites
- public social/content sources where permitted
- regional/local retail sources

These are candidate source classes, not a promise that every platform is technically or legally crawlable.

The source registry is the control plane. New sources must be discovered, assessed and approved before becoming production-trusted.

See `SOURCE_STRATEGY.md`.

### 4.4 Public Access and Compliance

Only collect publicly accessible information in accordance with source terms, robots directives, applicable law and technical restrictions.

Do not bypass login controls, CAPTCHAs, paywalls or anti-bot controls. A blocked source is recorded as blocked/manual-only rather than circumvented.

## 5. Source Discovery and Reuse

The platform has two related activities:

### Source discovery

Periodically discover new candidate domains, pages and promotion URLs using search engines, sitemaps, feeds, navigation and other permitted public discovery methods.

### Scheduled crawling

Normal runs primarily crawl already-approved sources and URL targets stored in the database.

This means the system learns its source universe instead of searching the entire web from scratch on every run.

A discovered source is **not automatically trusted**.

Lifecycle:

```text
DISCOVERED -> CANDIDATE -> ASSESSED -> APPROVED -> ACTIVE
                                      |             |
                                      |             +-> HEALTHY/WARNING/STALE/BLOCKED
                                      +-> DISABLED
```

## 6. Target Users

Marketing, Trade Marketing, Brand/Category Managers, Sales, Management and Data/Operations users.

## 7. Core Product Requirements

### PR-001 — Multi-Source Discovery

Discover candidate sources and relevant URLs, place them in a source/URL registry, and require assessment before production use.

### PR-002 — Source Registry

Store source type, domain, reliability, priority, crawl frequency, access status, adapter, health and history.

### PR-003 — Scheduled Source Crawling

Normal scheduled runs load active approved sources and due URL targets from PostgreSQL and crawl them according to source policy.

### PR-004 — Adaptive Crawling

Prioritize URLs using source priority, historical promotion yield, freshness requirement, recent content change, validity periods and failure/backoff state.

### PR-005 — Structured Extraction

Extract product, brand, competitor, price, mechanic, retailer, channel, geography, validity and conditions.

### PR-006 — Evidence

Every extracted commercial fact must be traceable to source evidence.

### PR-007 — Geographic Scope

Geography is first-class data. Preserve exact source wording, normalized inclusions and exclusions, and geography confidence.

Never default unknown geography to `Indonesia`.

### PR-008 — Regional Price Intelligence

The same SKU may have different prices/mechanics by geography, retailer or channel. Materially different observations must remain separate.

### PR-009 — Promotion Taxonomy

Normalize:

- DISCOUNT
- BUY_X_GET_Y
- MULTIBUY
- CASHBACK
- VOUCHER
- MEMBER_PRICE
- GIFT_WITH_PURCHASE
- BUNDLE
- MINIMUM_SPEND
- OTHER

Preserve original wording.

### PR-010 — Validity and Freshness

Track:

- start_date
- end_date
- first_seen_at
- last_seen_at
- last_verified_at

Default Top 10 freshness is 90 days, but an expired promotion must never be active merely because it was recently crawled.

### PR-011 — Quality Gate

A Top 10 candidate must have target-category relevance, current validity, <=90-day freshness, usable evidence, passed validation, sufficiently resolved identity/geography, and no unresolved material contradiction.

### PR-012 — Ranking

Rank only after the quality gate. Ranking uses explainable factors such as promotion strength, source reliability, freshness, relevance, evidence quality, confidence and commercial impact.

Display as `Impact Score`, never as accuracy/probability.

### PR-013 — Auditability

Users must be able to see source URL, source, crawl time, verification time, evidence, prices, mechanic, retailer/channel, geography, validity, conditions, confidence and ranking explanation.

### PR-014 — PostgreSQL Source of Truth

```text
Crawler -> PostgreSQL -> API -> UI
```

The UI must never contain production mock rows or generated fallback records.

## 8. Geography Requirements

Support commercial scopes including:

```text
NATIONAL
ISLAND_GROUP
REGION
PROVINCE
METRO
CITY
DISTRICT
STORE
STORE_GROUP
ONLINE
OTHER
UNKNOWN
```

Preserve both source geography and normalized scope. Do not silently expand `Jawa` into provinces or `Jabodetabek` into cities without an approved mapping.

Retailer/store exclusions must remain explicit.

## 9. Retailer and Channel

Retailer, channel and geography are independent dimensions.

Example:

```text
Retailer = Hypermart
Channel = OFFLINE_RETAIL
Geography = Jawa
```

Unknown values remain `UNKNOWN`/`NULL` rather than being guessed.

## 10. Commercial Calculations

Use source-stated and calculated discount separately. Use `NUMERIC(18,2)` for money. Do not automatically subtract cashback/vouchers from shelf price unless conditions support an effective-price calculation.

Capture conditions such as member-only, minimum spend/quantity, maximum quantity, payment method, app-only, voucher code, store exclusion and geography exclusion.

## 11. AI Requirements

AI must use structured output and must never invent missing facts.

At minimum, field confidence is required for product, brand, competitor, price, promotion, validity and geography.

AI/model/prompt/schema versions must be auditable.

## 12. Data Lifecycle

```text
DISCOVERED
  -> EXTRACTED
  -> VALIDATED
  -> RESOLVED
  -> DEDUPLICATED
  -> QUALITY_GATE
  -> ELIGIBLE
  -> ACTIVE / EXPIRED / UPCOMING

Any material ambiguity -> REVIEW_REQUIRED
```

Raw source documents and observations remain immutable.

## 13. Review Queue

Review triggers include unknown competitor, ambiguous product, price conflict, date conflict, geography ambiguity, missing evidence, low confidence, parser anomaly and suspected material duplicate.

Actions: approve, edit, reject, link entity, or mark source/parser issue.

## 14. Source Reliability

Reliability is configurable in `source_registry` and should be informed by source authority and observed quality.

Suggested starting classes:

| Tier | Source class | Starting range |
|---|---|---:|
| 1 | Official retailer/brand | 1.00 |
| 2 | Verified official marketplace | 0.85–0.95 |
| 3 | Established promotion intelligence | 0.70–0.85 |
| 4 | Established media | 0.60–0.80 |
| 5 | Public social/other | 0.40–0.70 |

These are defaults, not immutable truth.

## 15. Multi-Source Conflict Rules

If sources disagree:

1. retain both observations
2. compare timestamps
3. compare source reliability
4. compare geography
5. compare retailer/channel
6. determine whether they are actually different activities
7. send unresolved material conflicts to review

Never overwrite a source observation merely because another source is newer.

## 16. Non-Functional Requirements

- evidence over assumptions
- source failures visible
- no secret leakage
- configurable source adapters
- scalable server-side filtering
- PostgreSQL-backed API/UI
- auditable model/prompt versions
- compliant public collection only

## 17. Acceptance Criteria

1. Multiple source classes can be registered without changing canonical promotion tables.
2. A source can be disabled without deleting historical observations.
3. A URL target can be scheduled independently from its domain.
4. A successful crawl producing zero promotions is recorded as success, not failure.
5. A failed crawl is not interpreted as zero promotions.
6. Unchanged content can skip expensive AI extraction where safe.
7. Changed content produces a new observation after extraction/validation.
8. Multiple sources can support one canonical promotion.
9. Conflicting regional prices remain separate when commercially material.
10. Unknown geography never silently becomes nationwide.
11. Source reliability is configurable and auditable.
12. Discovery can find candidate new sources without automatically trusting them.
13. Normal scheduled runs primarily use the approved source/URL registry.
14. Expired promotions do not appear in the active Top 10.
15. Promotions older than 90 days do not appear in the default Top 10.
16. No verified promotion without usable evidence.
17. UI reads production data only from PostgreSQL through the API.
18. Source health and crawler failures are visible.
19. Ranking is explainable.

## 18. Explicit Non-Goals for MVP

- consumer checkout
- automatic coupon redemption
- private/login-only collection without approved access
- bypassing access controls
- modifying source websites
- writing to `dwh_prod`
- treating AI output as authoritative without validation
