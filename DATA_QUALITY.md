# DATA_QUALITY.md — Data Quality, Trust and Provenance

## 1. Objective

The platform is a decision-support system. A visually complete dashboard is less valuable than a smaller set of correct, traceable promotions.

The governing principle is:

> **Never invent a commercial fact. Preserve uncertainty and route material ambiguity to review.**

## 2. Quality Pipeline

```text
Raw document
   -> extraction
   -> field validation
   -> geography normalization
   -> entity resolution
   -> duplicate detection
   -> evidence check
   -> quality gate
   -> ranking
```

## 3. Required Evidence

A verified promotion must have usable source evidence for the important facts it displays.

At minimum:

```text
product
promotion mechanic
price/benefit
validity or reliable recency
geography when claimed
```

Evidence should include source URL and retrieval timestamp.

## 4. Source Reliability

Source reliability is stored in `source_registry` and may be revised based on observed source quality.

Starting guidance:

| Tier | Source | Starting reliability |
|---|---|---:|
| 1 | Official retailer/brand | 1.00 |
| 2 | Verified official marketplace | 0.85–0.95 |
| 3 | Established promotion intelligence | 0.70–0.85 |
| 4 | Established media | 0.60–0.80 |
| 5 | Public social/other | 0.40–0.70 |

These are configuration defaults, not facts about every website.

## 5. Field Confidence

AI confidence must not be treated as truth probability.

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

Low confidence should trigger review when the field is commercially material.

## 6. Geography Quality Rules

### Rule 1
Preserve exact source wording.

### Rule 2
Do not default unknown geography to Indonesia.

### Rule 3
Do not silently expand commercial areas into administrative regions.

### Rule 4
Store inclusions and exclusions separately.

### Rule 5
A geography contradiction that changes whether the promotion applies to a target market must trigger review.

Example:

```text
Observation A: Berlaku di Jawa
Observation B: Berlaku di Sumatera
```

Do not merge these as one nationwide promotion.

## 7. Price Quality Rules

- monetary values use `NUMERIC(18,2)`
- negative prices are invalid
- promo price below regular price is expected for ordinary discount mechanics
- promo price above regular price requires an explanation or different mechanic
- source-stated discount and calculated discount are stored separately
- cashback/voucher is not automatically treated as shelf-price reduction

## 8. Promotion Mechanic Quality

Normalize language but retain original wording.

Examples:

```text
Beli 1 Gratis 1 -> BUY_X_GET_Y (1,1)
Beli 2 Gratis 1 -> BUY_X_GET_Y (2,1)
Diskon 30%      -> DISCOUNT
2 pcs Rp20.000  -> MULTIBUY
```

If the wording is ambiguous, use `OTHER` and review rather than guessing.

## 9. Date Quality

- `end_date < start_date` is invalid
- an explicit expired date always beats a recent crawl for active-status calculation
- missing end date requires a strict recent-verification rule
- source timezone/local context must be respected where known
- all stored timestamps use `TIMESTAMPTZ`

## 10. Freshness

The default Top 10 uses:

```text
last_verified_at >= now - 90 days
```

But freshness alone does not mean active.

Active requires current validity plus freshness/quality eligibility.

For open-ended promotions, a recommended MVP verification window is 7 days.

## 11. Duplicate Quality

Potential duplicate matching should consider:

- product
- retailer
- channel
- promotion type
- mechanic parameters
- price
- validity
- geography inclusion
- geography exclusion
- material conditions

Two regional promotions are not duplicates merely because the product and retailer match.

## 12. Unknown Values

Use explicit unknowns:

```text
NULL
UNKNOWN
N/A
```

according to field semantics.

Never create placeholder competitors such as:

```text
FMCG Manufacturer
Competitor Brand
Unknown Company Ltd
```

unless that is literally the source text and is explicitly marked as unresolved.

## 13. Quality Gate

A record passes the production gate when:

```text
category eligible
AND current validity passes
AND freshness passes
AND evidence exists
AND no material validation error
AND identity is sufficiently resolved
AND geography is sufficiently understood
AND status != REJECTED
```

Anything else may remain stored for audit but must not appear as a verified Top 10 record.

## 14. Review Queue Thresholds

Create a review item for:

- overall confidence below configured threshold
- geography confidence below threshold
- price conflict
- validity conflict
- unresolved product
- unresolved competitor
- material duplicate uncertainty
- source parser anomaly
- missing evidence

Thresholds must be configuration, not scattered constants.

## 15. Source Failure Semantics

A failed crawl is not equivalent to zero promotions.

The source health model must distinguish:

```text
SUCCESS
FAILED
BLOCKED
STALE
NOT_RUN
```

The dashboard must show the source health state.

## 16. Data Quality Metrics

Track at least:

```text
crawl_success_rate
extraction_success_rate
evidence_coverage_rate
geography_resolution_rate
entity_resolution_rate
duplicate_rate
review_rate
active_promotion_count
stale_promotion_count
```

These metrics should be visible to operators.

## 17. Auditability

For every Top 10 record, an auditor should be able to answer:

1. Where did this promotion come from?
2. When was it crawled?
3. When was it last verified?
4. What text supports the price?
5. What text supports the promotion mechanic?
6. What text supports the geography?
7. What model/prompt extracted it?
8. Which validation rules passed/failed?
9. How was the product resolved?
10. Why did it rank where it did?

## 18. Data Quality Acceptance Tests

The following must be automated where practical:

- no verified promotion without evidence
- no negative monetary values
- no invalid date ranges
- no unknown geography silently converted to Indonesia
- no material regional duplicates merged
- no expired record in active Top 10
- no record older than 90 days in default Top 10
- no fake competitor placeholders
- source failures visible as failures
- UI values trace back to API/PostgreSQL
