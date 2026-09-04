# PRD.md — FMCG Competitor Promotion Intelligence

## 1. Product Vision

Build an AI-powered competitive promotion intelligence platform for the Indonesian FMCG snack market, initially focused on biscuits, crackers, cookies and wafers.

The product continuously collects publicly available promotion information, converts it into structured commercial observations, validates the facts against source evidence, resolves products/brands/competitors, preserves geographic scope, and presents the most important currently active activities to marketing, trade marketing, sales and management.

The system is a **decision-support product**. It must prefer an explicit unknown value over an invented value.

## 2. Primary Business Question

> What are the 10 most commercially important competitor promotions that are active now, recently verified, geographically understood, and supported by reliable evidence?

A promotion is not considered trustworthy unless the user can trace it to source evidence.

## 3. Business Outcomes

The platform should reduce manual competitor monitoring and enable users to understand:

- which competitor/brand is promoting
- which exact product/SKU/pack size is involved
- what promotion mechanic is being used
- regular vs promotional price
- effective discount where calculable
- retailer/channel
- geographic validity
- start/end validity
- source reliability
- when the observation was last verified
- why the activity is ranked highly

## 4. Scope

### 4.1 Initial Market

Indonesia.

### 4.2 Initial Categories

- Biscuit
- Cracker
- Cookie
- Wafer
- Sandwich biscuit
- Cream biscuit
- Sweet biscuit
- Savory cracker
- Closely related snack products only when explicitly relevant

### 4.3 Initial Source

The first production source is **Hemat.id**.

Do not confuse this with `hemat.co.id`.

The source adapter must preserve the source URL, retrieval time, exact evidence and source geography wording.

The architecture must allow additional sources later without changing the canonical data model.

### 4.4 Future Source Classes

- official retailer websites/catalogs
- official brand websites/stores
- verified marketplace stores
- promotion aggregators
- established media
- public social sources

Source priority is configurable. A source must not become trusted merely because an AI model extracted it successfully.

## 5. Target Users

### Marketing

Needs competitor activity, promotion intensity, pricing and regional differences.

### Trade Marketing

Needs retailer, channel, mechanic and geographic detail.

### Brand / Category Manager

Needs competitive landscape, price positioning and activity trends.

### Sales

Needs current retailer and regional promotions.

### Management

Needs a concise executive view of significant competitive activity.

### Data/Operations User

Needs source health, extraction quality, evidence and review queues.

## 6. Core Product Requirements

### PR-001 — Active Promotion Discovery

Discover promotions relevant to the target categories from configured sources.

### PR-002 — Structured Extraction

Extract product, brand, competitor, price, mechanic, retailer, geography, validity and conditions into structured fields.

### PR-003 — Evidence

Every extracted commercial fact must be traceable to source evidence.

### PR-004 — Geographic Scope

Geography is a first-class requirement, not a free-text afterthought.

The system must preserve:

1. exact source geography wording
2. normalized inclusion scopes
3. normalized exclusion scopes
4. geography confidence

Examples:

```text
Berlaku di Jawa
Berlaku di Jawa, Bali, Lombok
Berlaku di Jawa, Bali, Lombok, kecuali Indomaret Point
Berlaku di Jabodetabek, Palembang
```

Never default an unknown geography to `Indonesia`.

`Indonesia` can only be used when the source explicitly establishes national validity or an approved deterministic rule does so.

### PR-005 — Regional Price Intelligence

The same product can have different prices or mechanics by region. These must remain separate commercial observations.

Example:

```text
Roma Sari Gandum 108g

Jawa        Rp7,900   34% OFF
Sumatera   Rp8,500   29% OFF
Sulawesi   Rp9,900   23% OFF
```

Do not merge these into one promotion solely because product and retailer match.

### PR-006 — Promotion Taxonomy

Normalize equivalent language into controlled mechanics:

- `DISCOUNT`
- `BUY_X_GET_Y`
- `MULTIBUY`
- `CASHBACK`
- `VOUCHER`
- `MEMBER_PRICE`
- `GIFT_WITH_PURCHASE`
- `BUNDLE`
- `MINIMUM_SPEND`
- `OTHER`

Preserve the original promotion wording as evidence.

### PR-007 — Validity

The system must distinguish:

- `start_date`
- `end_date`
- `first_seen_at`
- `last_seen_at`
- `last_verified_at`

An active promotion must be currently valid according to its source evidence.

If an end date is absent, the promotion may only remain active while recent verification satisfies the configured freshness rule.

### PR-008 — 90-Day Default Freshness

The default Top 10 must use a maximum observation age of 90 days.

This is a business freshness rule, not a replacement for promotion validity.

A promotion observed within 90 days but already expired must not appear in the active Top 10.

### PR-009 — Quality Gate

Ranking must happen after eligibility validation.

A candidate is eligible for the default Top 10 only when:

- target category is confirmed
- current validity is confirmed
- observation is within 90 days
- source is allowed
- required evidence exists
- critical price/date/geography contradictions are absent
- product/brand/retailer identity is sufficiently resolved
- record is not rejected

### PR-010 — Top 10 Ranking

Rank eligible promotions using an explainable composite score incorporating configurable factors such as:

- promotion strength
- source reliability
- freshness
- category relevance
- AI extraction confidence
- evidence quality
- commercial impact

The score must not be described as probability or accuracy.

Display it as `Impact Score` or equivalent.

### PR-011 — Auditability

A user must be able to open a promotion and see:

- source
- source URL
- crawl timestamp
- verification timestamp
- exact evidence text
- product/brand/competitor
- prices
- mechanic
- retailer/channel
- geographic scope and exclusions
- validity
- confidence by field
- ranking factors

### PR-012 — PostgreSQL as UI Source of Truth

The UI must never contain hard-coded production promotion data.

The data path must be:

```text
PostgreSQL -> API -> UI
```

The crawler writes through the ingestion pipeline into PostgreSQL.

If the database is empty, the UI must display an empty state, not demo data.

## 7. Geography Requirements

### 7.1 Supported Geography Concepts

The system must support commercial scopes including, but not limited to:

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
UNKNOWN
```

Examples include:

- Indonesia
- Jawa
- Sumatera
- Kalimantan
- Sulawesi
- Bali
- Lombok
- Jabodetabek
- Palembang
- individual cities
- individual store/outlet groups

### 7.2 Source vs Normalized Geography

Always retain both.

```text
source_text = "Berlaku di Jawa, Bali, Lombok, kecuali Indomaret Point"

normalized_includes = [Jawa, Bali, Lombok]
normalized_excludes = [Indomaret Point]
```

The source text is immutable evidence. Normalized geography can be corrected through controlled mapping.

### 7.3 No Silent Geographic Expansion

Do not infer every province/city inside a commercial region unless an explicit approved mapping is configured.

### 7.4 Geography Conflict

If different source observations disagree on geography, keep both observations and flag the canonical promotion for review if the difference changes commercial applicability.

## 8. Retailer and Channel Requirements

Retailer, channel and geography are separate dimensions.

For example:

```text
Retailer = Hypermart
Channel  = Offline Retail
Geography = Jawa
```

must not be represented as one free-text value.

Channel must use a controlled taxonomy, for example:

- `OFFLINE_RETAIL`
- `ONLINE_RETAILER`
- `MARKETPLACE`
- `OFFICIAL_BRAND_STORE`
- `OTHER`
- `UNKNOWN`

Unknown channel must remain `UNKNOWN`/`N/A`; never infer it from the retailer name alone unless an approved deterministic mapping exists.

## 9. Promotion Mechanics and Commercial Calculations

### Discount

If both regular and promo prices are known, calculated discount is:

```text
(regular_price - promo_price) / regular_price * 100
```

Preserve both the source-stated discount and calculated discount when both exist.

### Buy X Get Y

Store `buy_quantity` and `free_quantity` separately.

An effective discount may be calculated for comparable unit economics, but must be labeled as calculated rather than source-stated.

### Multi-buy

Store qualifying quantity and promotional price/total where available.

### Cashback / Voucher

Do not automatically subtract cashback or voucher from shelf price. Store the benefit separately and calculate an effective price only when eligibility conditions are explicit.

### Conditions

Capture:

- member-only
- minimum purchase amount
- minimum purchase quantity
- maximum quantity
- payment method
- app-only
- voucher code
- store exclusion
- geography exclusion
- other conditions

## 10. Source Reliability

Reliability is configurable per source and versioned where necessary.

Suggested starting tiers:

| Tier | Source class | Default range |
|---|---|---:|
| 1 | Official retailer/brand | 1.00 |
| 2 | Verified official marketplace | 0.85–0.95 |
| 3 | Established promotion intelligence | 0.70–0.85 |
| 4 | Established media | 0.60–0.80 |
| 5 | Public social/other | 0.40–0.70 |

These are starting values only. Actual reliability must be configurable in the database.

## 11. AI Requirements

AI extraction must use structured output and deterministic post-validation.

AI must never invent missing fields.

For every important field, the extraction result should be able to provide:

```text
value
confidence
source evidence reference
```

At minimum, confidence should be available for:

- product
- brand
- competitor
- price
- promotion mechanic
- validity
- geography

Low-confidence or contradictory records go to `review_queue`.

## 12. Data Lifecycle

```text
DISCOVERED
   |
   v
EXTRACTED
   |
   v
VALIDATED
   |
   +----> REVIEW_REQUIRED
   |
   v
RESOLVED
   |
   v
DEDUPLICATED
   |
   v
ELIGIBLE
   |
   v
ACTIVE / EXPIRED / UPCOMING
```

Observations remain immutable. Canonical promotions may be updated as new observations arrive.

## 13. Review Queue

The system must create review items for conditions such as:

- unknown competitor
- ambiguous product
- price conflict
- date conflict
- geography ambiguity
- source parsing failure
- missing evidence
- low AI confidence
- suspected duplicate with material differences

Review actions:

- approve
- edit
- reject
- link to canonical entity
- mark source/parser issue

## 14. User Experience Requirements

The product should look and behave like a professional enterprise intelligence application.

### Navigation

```text
Overview
Promotions
Regional Pricing
Competitors
Sources
Review Queue
Settings
```

### Overview

Show:

- active promotions
- competitors tracked
- brands monitored
- retailers monitored
- expiring soon
- promotion activity trend
- competitor activity intensity
- regional distribution
- source health

### Promotions

Provide a filterable table and right-side detail drawer.

Primary filters:

- category
- competitor
- brand
- retailer
- mechanic
- geography
- validity
- source

### Regional Pricing

Compare product price/promotion by geographic scope. Missing evidence must display as `No evidence`, not zero.

### Detail Drawer

Must show source, evidence, geography, validity, conditions, confidence and `Open source` action.

### Source Health

Show last successful crawl, failure rate, current status and freshness.

### Empty / Error / Stale States

Every page must distinguish:

- no matching data
- database unavailable
- source unavailable
- crawler failed
- stale data

Never use fake rows to fill the screen.

## 15. Non-Functional Requirements

### Accuracy

No unsupported commercial facts.

### Freshness

Default active intelligence is no older than 90 days and must respect actual promotion validity.

### Traceability

Every canonical promotion must be traceable to one or more source observations.

### Reliability

Crawl failures must be observable and retryable.

### Security

Secrets must never be committed. Database credentials must be least privilege.

### Performance

Top 10 and common filter queries should be indexed and return quickly on expected production volumes.

### Extensibility

New sources, retailers, promotion mechanics and geography mappings must be configurable without rewriting the core model.

## 16. Acceptance Criteria

The MVP is accepted only when all are true:

1. A real Hemat.id page can be crawled.
2. Raw source evidence is persisted.
3. AI extraction produces structured fields.
4. Price/date/mechanic/geography validation runs.
5. Exact source geography is preserved.
6. Regional observations are not incorrectly merged.
7. Promotion evidence can be opened from the UI.
8. Expired promotions do not appear in the default Top 10.
9. Promotions older than 90 days do not appear in the default Top 10.
10. Records without usable evidence cannot be presented as verified.
11. The UI reads from PostgreSQL through the API and contains no production mock rows.
12. A PostgreSQL outage produces a visible error state.
13. A crawler outage is visible in source health.
14. A promotion with ambiguous geography enters review rather than silently becoming nationwide.
15. Top 10 ranking is explainable.

## 17. Explicit Non-Goals for MVP

- automatic purchase or coupon redemption
- consumer checkout
- competitor sentiment analysis
- private/login-only data collection without approved access
- bypassing anti-bot controls
- modifying source websites
- writing into `dwh_prod`
- treating AI output as authoritative without validation
