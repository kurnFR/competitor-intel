# DATA_QUALITY.md — Data Quality, Trust and Provenance

## 1. Objective

The platform is a decision-support system. A smaller set of correct, traceable promotions is more valuable than a visually complete dashboard.

> **Never invent a commercial fact. Preserve uncertainty and route material ambiguity to review.**

## 2. Quality Pipeline

```text
Source discovery
   -> source assessment
   -> approved source/URL
   -> crawl
   -> raw document
   -> extraction
   -> field validation
   -> geography normalization
   -> entity resolution
   -> duplicate detection
   -> evidence check
   -> quality gate
   -> ranking
```

## 3. Source Quality

A source has two separate dimensions:

1. **Authority/reliability** — how trustworthy the source is for a commercial fact.
2. **Operational health** — whether the source was successfully crawled recently.

A high-authority source can be operationally stale. A successfully crawled low-authority source is not automatically trustworthy.

Track:

```text
source_tier
reliability_score
crawl_success_rate
blocked_rate
last_success_at
consecutive_failures
```

## 4. Source Discovery Quality

Discovered sources are candidates, not trusted data.

Required before approval:

- public relevance to target categories
- identifiable source/domain
- access permitted
- source type classified
- reliability tier proposed
- crawl method understood
- test extraction/evidence available where practical

Discovery must never directly publish canonical promotions.

## 5. Required Evidence

A verified promotion must have usable evidence for:

```text
product
promotion mechanic
price/benefit
validity or reliable recency
geography when claimed
```

Evidence includes source URL and retrieval timestamp.

## 6. Field Confidence

Store separate confidence where practical:

```text
product_confidence
brand_confidence
competitor_confidence
price_confidence
promotion_confidence
validity_confidence
geography_confidence
```

Confidence is extraction/model confidence, not factual probability.

## 7. Geography Quality Rules

1. Preserve exact source wording.
2. Never default unknown geography to Indonesia.
3. Never silently expand commercial areas into administrative regions.
4. Store inclusions and exclusions separately.
5. Geography contradictions that change applicability trigger review.
6. Geography is part of promotion matching/deduplication.

Example:

```text
Observation A: Jawa / Rp7,900
Observation B: Sumatera / Rp8,500
```

Do not merge them into one nationwide promotion.

## 8. Price Quality Rules

- monetary values use `NUMERIC(18,2)`
- negative prices are invalid
- promo price above regular price requires explanation/mechanic
- stated and calculated discounts are separate
- cashback/voucher is not automatically shelf-price reduction
- conflicting prices from different regions/sources remain observations until resolved

## 9. Promotion Mechanic Quality

Normalize equivalent language while retaining source wording.

```text
Beli 1 Gratis 1 -> BUY_X_GET_Y (1,1)
Beli 2 Gratis 1 -> BUY_X_GET_Y (2,1)
Diskon 30%      -> DISCOUNT
2 pcs Rp20.000  -> MULTIBUY
```

Ambiguous wording becomes `OTHER`/review rather than a guessed mechanic.

## 10. Date Quality

- end date before start date is invalid
- explicit expiry beats recent crawl for active status
- missing end date requires strict recent verification
- source timezone/local context must be respected
- timestamps use `TIMESTAMPTZ`

## 11. Freshness

Default Top 10:

```text
last_verified_at >= now - 90 days
```

Freshness does not equal active validity.

Open-ended promotions should use a stricter verification window, recommended 7 days for MVP.

## 12. Multi-Source Conflict Rules

When sources disagree:

1. retain all useful observations
2. compare timestamps
3. compare source reliability
4. compare geography
5. compare retailer/channel
6. determine whether activities are actually different
7. create review when unresolved and material

Do not overwrite lower-tier observations; preserve them for audit.

## 13. Duplicate Quality

Candidate matching considers:

- product
- retailer
- channel
- mechanic
- mechanic parameters
- price
- validity
- geography inclusion
- geography exclusion
- material conditions

Two sources may support one canonical promotion. Material regional/channel/price differences must not be merged away.

## 14. Unknown Values

Use `NULL`, `UNKNOWN` or `N/A` according to semantics.

Never create fake competitors such as `FMCG Manufacturer` merely to fill a UI field.

## 15. Quality Gate

```text
category eligible
AND current validity passes
AND freshness passes
AND evidence exists
AND no material validation error
AND identity sufficiently resolved
AND geography sufficiently understood
AND source is approved
AND status != REJECTED
```

Anything else may remain stored for audit but must not appear as verified Top 10.

## 16. Review Queue

Create review items for low confidence, geography ambiguity/conflict, price conflict, date conflict, unresolved identity, material duplicate uncertainty, parser anomalies and missing evidence.

Thresholds are configuration, not scattered constants.

## 17. Source Failure Semantics

A failed crawl is not equivalent to zero promotions.

```text
SUCCESS
FAILED
BLOCKED
STALE
NOT_RUN
```

The dashboard must show source health.

## 18. Data Quality Metrics

Track:

```text
source_discovery_acceptance_rate
crawl_success_rate
extraction_success_rate
evidence_coverage_rate
geography_resolution_rate
entity_resolution_rate
duplicate_rate
review_rate
source_conflict_rate
active_promotion_count
stale_promotion_count
```

## 19. Auditability

For every Top 10 record, answer:

1. Where did it come from?
2. Which source and URL?
3. When crawled?
4. When last verified?
5. What supports price?
6. What supports mechanic?
7. What supports geography?
8. What model/prompt extracted it?
9. Which validation rules passed/failed?
10. How was identity resolved?
11. Why did it rank where it did?

## 20. Acceptance Tests

Automate where practical:

- no verified promotion without evidence
- no negative monetary values
- no invalid date ranges
- no unknown geography silently converted to Indonesia
- no material regional duplicates merged
- no expired record in active Top 10
- no record older than 90 days in default Top 10
- no fake competitor placeholders
- source failures visible as failures
- candidate sources cannot become trusted without approval
- UI values trace back to API/PostgreSQL
