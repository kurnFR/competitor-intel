# UI_UX_DESIGN.md — Professional Enterprise Dashboard

## 1. UX Goal

The product should feel like a professional enterprise intelligence application: dense enough for commercial users, clear enough for management, and transparent enough for data-quality review.

Priorities:

1. trust
2. fast scanning
3. comparison
4. evidence
5. freshness
6. regional understanding
7. explainability
8. source transparency

## 2. Information Architecture

```text
Overview
Promotions
Regional Pricing
Competitors
Sources
Review Queue
Settings
```

## 3. Global Header

Show product name, actual data freshness, environment, Refresh and Scan now. If source discovery is available, expose it separately as `Discover Sources` for authorized users.

Do not use a generic `Live System` badge without a real freshness timestamp.

## 4. Overview Page

Show KPI cards for active promotions, competitors, brands, retailers, expiring <=7 days, and source health.

Recommended sections:

1. promotion activity trend
2. top competitor activity
3. regional distribution
4. Top 10 active promotions
5. expiring soon
6. source health

## 5. Promotions Page

Filters:

```text
Category | Competitor | Brand | Retailer | Mechanic | Geography | Validity | Source
```

Show result count and last refresh time. Use server-side filtering/pagination.

Recommended primary columns:

```text
Rank
Competitor / Brand
Product
Promotion
Promo Price
Saving
Retailer
Area
Valid Until
Impact Score
```

Do not expose every audit field in the main table.

## 6. Promotion Table UX

- compact rows
- highlight mechanic and promo price
- explicitly show `No evidence` / `Unknown`
- never use zero for missing data
- expiry urgency must not rely on color alone
- sort by impact, expiry and latest verification
- server-side pagination

## 7. Promotion Detail Drawer

Open a right-side drawer without losing list context.

```text
PRODUCT
Brand / manufacturer
Product / variant / pack size

PROMOTION
Mechanic
Regular price
Promo price
Discount
Conditions

WHERE
Retailer
Channel
Included areas
Excluded areas
Source geography wording

WHEN
Valid from
Valid until
First seen
Last seen
Last verified

TRUST
Source
Source tier/reliability
AI confidence by field
Validation status

EVIDENCE
Supporting quotes
Source URL
Open source

RANKING
Impact score
Why this promotion ranks highly
```

## 8. Evidence UX

Evidence should be visible without forcing users to read raw HTML.

```text
PRICE
"Rp7.900"

GEOGRAPHY
"Berlaku di Jawa"

VALIDITY
"Periode 1–3 September 2026"
```

Provide an `Open source` action.

## 9. Field Confidence

Show field-level confidence rather than only one opaque score.

```text
Product      98% ✓
Price        99% ✓
Promotion    97% ✓
Geography    95% ✓
Validity     91% ⚠
Competitor   82% ⚠
```

Confidence is extraction/model confidence, not factual probability.

## 10. Regional Pricing Page

Select a product/SKU and compare verified observations by geography, retailer and channel.

| Area | Regular | Promo | Discount | Retailer | Verified |
|---|---:|---:|---:|---|---|
| Jawa | Rp11,990 | Rp7,900 | 34% | Hypermart | 10:42 |
| Sumatera | Rp12,500 | Rp8,500 | 32% | Hypermart | 10:39 |
| Sulawesi | No evidence | — | — | Hypermart | — |

`No evidence` does not mean no promotion exists.

## 11. Geography UX

Show geography as a compact badge and expose inclusions/exclusions in the detail drawer.

```text
Jawa +2 areas

Included
✓ Jawa
✓ Bali
✓ Lombok

Excluded
× Indomaret Point
```

Always expose source wording. Never display a silently inferred nationwide scope.

## 12. Source Registry / Sources Page

This page is both an operational view and a controlled source-management interface.

Show:

```text
Source
Type
Status
Reliability
Priority
Last successful crawl
Last failure
Success rate
Active URLs
Promotions found
```

Example:

```text
Hemat.id             Active   0.78   Healthy
Supermarket A        Active   0.94   Healthy
Brand X              Candidate  —    Awaiting approval
Marketplace Y        Blocked   —    Blocked
```

Separate these actions:

```text
Scan approved sources
Discover new sources
Review candidates
```

A discovered source must not automatically become trusted.

## 13.1 Source Candidate Detail

Show:

- discovered domain/URL
- source class
- discovery method
- first discovered time
- public-access status
- proposed adapter
- proposed reliability tier
- evidence of relevance
- assessment notes

Actions:

```text
Approve
Reject
Disable
Mark Manual Only
```

## 14. Review Queue UX

Prioritize by commercial risk:

```text
HIGH  Geography conflict
HIGH  Price conflict
HIGH  Unknown competitor
MED   Product ambiguity
MED   Low extraction confidence
LOW   Non-critical metadata
```

Show side-by-side:

```text
Source evidence | AI extraction | Current value
```

Actions: Approve, Edit, Reject, Link entity.

## 15. Search

Global search should support product, brand, competitor, retailer, geography, source and mechanic.

## 16. Loading / Empty / Error / Stale

Every page must distinguish loading, empty, error and stale states.

Example empty:

```text
No active promotions match these filters.
Try removing Geography or Retailer filters.
```

Example error:

```text
We couldn't load promotion data.
PostgreSQL/API is currently unavailable.
[Retry]
```

Example stale:

```text
Data may be stale.
Last successful source crawl: 6h 18m ago.
```

Never insert fake records.

## 17. Refresh vs Scan vs Discover

`Refresh` reloads canonical PostgreSQL data.

`Scan now` crawls active approved source targets.

`Discover sources` searches for candidate sources/URLs and adds them to the assessment queue; it does not publish them automatically.

## 18. Scan Progress UX

```text
Scan in progress

Approved sources       12
URLs scheduled          86
Pages fetched           73
Changed documents       31
Promotions found        19
Validated               14
Review required          5
```

Do not claim completion until the backend job reports completion.

## 19. Ranking UX

Display technical `rank_score` as `Impact Score`.

Provide an explanation:

```text
Why #1?
• strong promotion mechanic
• relevant competitor
• reliable source
• recently verified
• broad verified geographic scope
• strong evidence
```

Never imply the score is accuracy.

## 20. Visual Design Principles

- restrained enterprise palette
- strong typography hierarchy
- high information density without clutter
- consistent spacing
- subtle borders/elevation
- accessible contrast
- keyboard-friendly controls
- visible focus states
- responsive layout
- color supplementary to text/icons

## 21. Accessibility

Target WCAG 2.1 AA behavior where practical: keyboard navigation, semantic controls, sufficient contrast, visible focus, labels, non-color status indicators and readable number/date formats.

## 22. Data Display Rules

- IDR: `Rp7.900`
- percentage: `34%`
- unknown: `Unknown`
- no evidence: `No evidence`
- not applicable: `N/A`
- never show `0` for missing commercial facts
- local display timezone with precise timestamp in audit detail

## 23. Responsive Behavior

Desktop is primary. At narrow widths, preserve Product, Promotion, Promo Price, Area and Validity; move audit fields into the drawer.

## 24. Security UX

Do not expose database credentials, API keys or internal stack traces. Destructive source-management actions require confirmation.

## 25. UI Acceptance Criteria

1. Production data comes from PostgreSQL through the API.
2. No production mock rows exist.
3. Promotion evidence is reachable within two clicks.
4. Geography inclusions/exclusions are visible.
5. Last verified time is visible.
6. Regional price comparison is possible.
7. Source status and freshness are visible.
8. Discovery is clearly separated from approved crawling.
9. Empty/error/stale states are explicit.
10. Refresh, Scan and Discover have distinct meanings.
11. Top 10 ranking is explainable.
12. The interface remains usable with thousands of observations.
