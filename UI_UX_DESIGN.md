# UI_UX_DESIGN.md — Professional Enterprise Dashboard

## 1. UX Goal

The product should feel like a professional enterprise intelligence application: dense enough for commercial users, clear enough for management, and transparent enough for data-quality review.

The interface must prioritize:

1. trust
2. fast scanning
3. comparison
4. evidence
5. freshness
6. regional understanding
7. explainability

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

Keep operational pages separate from administrative settings.

## 3. Global Header

Show:

- product name
- current data freshness
- current environment
- Refresh action
- Scan now action
- user/profile area if authentication exists

Example:

```text
Competitor Promotion Intelligence     ● Data current
Last successful crawl: 10:44 WIB       [Refresh] [Scan now]
```

Do not use a generic `Live System` badge without an actual freshness timestamp.

## 4. Overview Page

### KPI cards

```text
Active Promotions
Competitors Tracked
Brands Monitored
Retailers Monitored
Expiring <= 7 Days
```

Each KPI should have a clear definition and optional click-through.

### Recommended sections

1. Promotion activity trend — last 30 days
2. Top competitor activity
3. Regional distribution
4. Top 10 active promotions
5. Expiring soon
6. Source health

## 5. Promotions Page

### Filter bar

Use compact, multi-select filters:

```text
Category | Competitor | Brand | Retailer | Mechanic | Geography | Validity | Source
```

Provide:

- clear all
- saved filter state if later implemented
- result count
- last refreshed timestamp

### Table

Recommended columns:

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

Do not expose every audit field in the primary table.

## 6. Promotion Table UX

- use compact rows
- highlight promotion mechanic and promo price
- show `No evidence` or `Unknown` explicitly
- never use zero to represent missing data
- show expiry urgency with a non-color-only indicator
- allow sorting by impact, expiry and latest verification
- keep pagination/server-side filtering for scale

## 7. Promotion Detail Drawer

Clicking a row should open a right-side drawer without losing the list context.

Recommended structure:

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
Last seen
Last verified

TRUST
Source
Source tier/reliability
AI confidence by field
Validation status

EVIDENCE
Exact supporting quotes
Source URL
Open source

RANKING
Impact score
Why this promotion ranks highly
```

## 8. Evidence UX

Evidence should be visible without making users read raw HTML.

For example:

```text
PRICE
"Rp7.900"

GEOGRAPHY
"Berlaku di Jawa"

VALIDITY
"Periode 1–3 September 2026"
```

Provide an `Open source` action to the original public page.

## 9. Field Confidence

Prefer field-level confidence over one opaque score.

```text
Product      98%  ✓
Price        99%  ✓
Promotion    97%  ✓
Geography    95%  ✓
Validity     91%  ⚠
Competitor   82%  ⚠
```

Explain that confidence is model/extraction confidence, not factual probability.

## 10. Regional Pricing Page

This page is a key differentiator.

User selects a product/SKU and sees comparable observations:

| Area | Regular | Promo | Discount | Retailer | Verified |
|---|---:|---:|---:|---|---|
| Jawa | Rp11,990 | Rp7,900 | 34% | Hypermart | 10:42 |
| Sumatera | Rp12,500 | Rp8,500 | 32% | Hypermart | 10:39 |
| Sulawesi | No evidence | — | — | Hypermart | — |

`No evidence` means the system has no verified observation. It does not mean no promotion exists.

## 11. Geography UX

Show geography as a compact badge plus details.

Example:

```text
Jawa
+2 areas
```

On expansion:

```text
Included
✓ Jawa
✓ Bali
✓ Lombok

Excluded
× Indomaret Point
```

Always show source wording in the detail view.

## 12. Expiry UX

Use clear relative labels:

```text
Expires today
Expires tomorrow
2 days left
7 days left
```

Do not rely on color alone. Include text/icon semantics.

## 13. Source Health Page

For each source show:

```text
Source
Status
Last successful crawl
Last failure
Success rate
Consecutive failures
Documents collected
Promotions extracted
```

Example states:

```text
Healthy
Warning
Stale
Failed
Blocked
Not configured
```

## 14. Review Queue UX

Prioritize by commercial risk.

```text
HIGH  Geography conflict
HIGH  Price conflict
HIGH  Unknown competitor
MED   Product ambiguity
MED   Low extraction confidence
LOW   Non-critical metadata
```

Review drawer should show side-by-side:

```text
Source evidence | AI extraction | Current value
```

Actions:

```text
Approve
Edit
Reject
Link entity
```

## 15. Search

Global search should support:

- product
- brand
- competitor
- retailer
- geography
- promotion mechanic

Search should return the same canonical data used by the list pages.

## 16. Loading / Empty / Error / Stale States

Every data page must define all four states.

### Loading

Use skeleton rows/cards.

### Empty

Example:

```text
No active promotions match these filters.
Try removing Geography or Retailer filters.
```

### Error

Example:

```text
We couldn't load promotion data.
PostgreSQL/API is currently unavailable.
[Retry]
```

### Stale

Example:

```text
Data may be stale.
Last successful source crawl: 6h 18m ago.
```

Never insert fake records to avoid an empty screen.

## 17. Refresh vs Scan

`Refresh`:

> Reload canonical data already stored in PostgreSQL.

`Scan now`:

> Start source collection and extraction.

After Scan now, show progress and a completion summary.

## 18. Scan Progress UX

```text
Scan in progress

Hemat.id
██████████████░░ 82%

Pages fetched        23
Documents changed    17
Promotions found      9
Validated             7
Review required       2
```

Do not claim a scan is complete until the backend job reports completion.

## 19. Ranking UX

Rename technical `rank_score` to `Impact Score` in the business UI.

Provide an explanation:

```text
Why #1?
• 34% price reduction
• high competitor relevance
• reliable source
• verified recently
• broad geographic scope
• strong evidence
```

Never imply that 89 points means 89% accuracy.

## 20. Visual Design Principles

- restrained enterprise color palette
- strong typography hierarchy
- high information density without clutter
- consistent spacing
- subtle borders and elevation
- accessible contrast
- keyboard-friendly controls
- visible focus states
- responsive layout
- color is supplementary, not the only status signal

The existing dark theme can remain, but it should be treated as an enterprise theme rather than a decorative gaming dashboard.

## 21. Accessibility

Target WCAG 2.1 AA behavior where practical:

- keyboard navigation
- semantic buttons/links
- sufficient contrast
- visible focus
- labels for filters
- non-color status indicators
- readable number/date formats

## 22. Data Display Rules

- IDR format: `Rp7.900`
- percentages: `34%`
- unknown: `Unknown`
- no evidence: `No evidence`
- not applicable: `N/A`
- never show `0` for missing commercial facts
- dates use local display timezone while retaining precise UTC timestamps in audit detail

## 23. Responsive Behavior

Desktop is the primary target for commercial users.

At narrower widths:

- collapse secondary columns
- preserve Product, Promotion, Promo Price, Area and Validity
- move audit fields into the drawer
- keep filters accessible through a filter panel

## 24. Security UX

Do not expose:

- database credentials
- LLM API keys
- internal stack traces
- sensitive infrastructure details

Admin actions should show confirmation for destructive changes.

## 25. UI Acceptance Criteria

The UI is ready when:

1. All production promotion data comes from PostgreSQL through the API.
2. No production mock rows exist.
3. A promotion can be traced to source evidence in two clicks or fewer.
4. Geography and exclusions are visible.
5. Last verified time is visible.
6. Regional price comparison is possible.
7. Empty/error/stale states are explicit.
8. Refresh and Scan now are clearly different.
9. Top 10 ranking is explainable.
10. The interface remains usable with hundreds/thousands of promotion records.
