# PRD — FMCG Competitor Promotion Intelligence Platform

## 1. Product Goal

Build a production-grade competitor intelligence platform for biscuit, cracker and adjacent FMCG categories in Indonesia.

The platform continuously discovers and monitors reliable public sources, extracts competitor products, prices, promotions and commercial conditions, validates the information, preserves evidence and geography, and presents the most relevant currently valid activities through a PostgreSQL-backed web application.

This is a **multi-source intelligence platform**, not a Hemat.id scraper.

## 2. Primary Business Questions

- What competitor promotions are active now?
- Which products and pack sizes are involved?
- What is the normal and promotional price?
- What is the promotion mechanic: Buy 1 Get 1, discount, bundle, cashback, voucher, multi-buy, etc.?
- Which retailer/channel is running it?
- Where is it valid: Indonesia, island, province, city, store, or online-only?
- When does it start and end?
- Which sources support the claim?
- How recently was it verified?
- What are the strongest/highest-impact activities in the current Top 10?
- Are prices or mechanics different by region or channel?

## 3. Target Users

### Marketing Manager
Needs a fast view of active competitor activity and implications.

### Trade Marketing / Sales
Needs retailer, channel and regional price/promotion intelligence.

### Category Manager
Needs product, competitor, pack-size and promotion comparisons.

### Data/Operations User
Needs source health, crawl status, evidence, validation and review workflows.

## 4. Scope

### In scope

- Biscuit and cracker competitor intelligence
- Product and SKU identification
- Price and discount extraction
- Promotion mechanic extraction
- Promotion validity
- Retailer/channel identification
- Regional/local geography
- Multi-source collection
- Source discovery and registry
- URL target registry
- Evidence/provenance
- AI-assisted structured extraction
- Deterministic validation
- Entity resolution and deduplication
- Conflict handling
- Top 10 active activities
- PostgreSQL persistence
- API and professional dashboard
- Source health and review queue

### Initial source categories

- Official manufacturer and brand websites
- Official modern-trade and retailer websites
- Regional/local retailer websites
- Public e-commerce and marketplace pages where collection is permitted
- Public promotion/catalog/flyer pages
- Established news/media pages
- Other approved public sources discovered by the system

Hemat.id is an initial source adapter only. It is not the exclusive source.

## 5. Public Collection Policy

The system may use standard HTTP clients, browser automation, JavaScript rendering, public feeds, sitemaps and publicly exposed endpoints to collect information that is accessible without authentication and may be collected under applicable source restrictions.

The system must not circumvent authentication, CAPTCHA, paywalls, private data, private APIs or technical controls specifically intended to restrict automated access.

If a source blocks automated collection, mark it blocked/restricted and use another permitted source or manual review. Do not interpret a failed crawl as zero promotions.

## 6. Source Discovery and Registry

Source discovery is a product capability.

```text
Web discovery
   ↓
Candidate source / URL
   ↓
Relevance + access assessment
   ↓
Candidate registry
   ↓
Approval
   ↓
Active source / URL
```

Discovery must not automatically trust every search result.

Normal scheduled scans primarily use approved source and URL registries. Discovery runs separately on a configurable schedule to find new sources and useful URLs.

The source registry must record domain, source type, authority/reliability, access mode/status, adapter, crawl priority/frequency, health and active state.

The URL registry must record canonical URL, page type, crawl priority/frequency, content hash, last crawl/success, failure state and next crawl time.

A source or URL can be disabled without deleting historical observations.

## 7. Core Data Model

The product separates:

```text
Source Control
  source_registry
  source_urls
  crawl_jobs
  crawl_documents

Observations
  extraction_runs
  promotion_observations

Master Data
  competitors
  brands
  products
  retailers
  geography_reference

Canonical Commercial Data
  promotions
  promotion_geographies
  promotion_conditions

Provenance and Quality
  promotion_evidence
  validation_results
  entity_mapping
  review_queue
```

Observations are immutable. Canonical promotions are derived from observations and can be re-evaluated as new evidence arrives.

## 8. Promotion Fields

Minimum commercial fields:

- competitor
- brand
- product
- SKU/pack size where available
- normal/list price where available
- promotional price
- currency
- discount amount/percentage
- mechanic
- mechanic parameters
- retailer
- channel
- geography
- valid_from
- valid_until
- conditions
- status
- evidence
- confidence
- first_seen_at
- last_seen_at
- last_verified_at

Unknown information must remain unknown rather than inferred.

## 9. Geography Requirements

Geography is first-class data.

The system must support Indonesia, island/region, province, city, retailer region, store and online-only scope.

Preserve source wording exactly and store normalized geography separately.

Examples include Jawa, Sumatera, Kalimantan, Sulawesi, Jabodetabek, Jakarta, selected stores and online only.

Never assume missing geography means nationwide. Never expand a regional statement into nationwide coverage without evidence.

## 10. Regional Pricing

Regional price differences must remain visible.

```text
Product X
Jawa       Rp7,900
Sumatera   Rp8,500
Kalimantan Rp9,500
Sulawesi   Rp9,900
```

These must not be collapsed into one price merely because product and promotion names match.

## 11. Evidence and Provenance

Every verified commercial fact must be traceable to source evidence.

Evidence should support, where possible, product identity, price, promotion mechanic, validity, geography and retailer/channel.

Store source URL, retrieval time, evidence excerpt/location and content/document reference.

## 12. AI Extraction

AI converts source documents into structured candidate observations.

AI must not invent prices, dates, geography, promotion conditions or product identity.

Each extraction stores model, prompt/schema version, status and confidence.

Deterministic validation happens after AI extraction.

## 13. Validation and Quality Gate

Before ranking, records must pass quality checks for current commercial validity, evidence availability, source approval, target category, identity resolution, geography quality, price validity, date consistency and material contradiction.

An explicit expired end date overrides crawl freshness.

## 14. Top 10 Definition

The Top 10 represents the strongest currently eligible competitor activities, not merely the ten newest scraped rows.

Eligibility requires:

```text
commercially active
AND
last_verified_at within configured freshness window (default 90 days)
AND
evidence exists
AND
source approved/active
AND
quality gate passed
AND
identity sufficiently resolved
AND
geography sufficiently understood
AND
no material unresolved contradiction
```

Ranking uses an explainable `Impact Score` based on configurable factors such as promotion strength, price impact, source authority, recency, reach/geographic scope and strategic relevance.

## 15. Freshness vs Validity

These are separate concepts:

```text
last_successful_crawl_at = source was collected
last_seen_at             = activity was observed
last_verified_at         = extracted facts were validated
valid_from / valid_until = commercial validity
```

A promotion verified yesterday can still be expired. An open-ended promotion may have no expiry date but must be re-verified periodically.

## 16. Multi-Source Conflict

When two sources disagree:

1. retain both observations
2. compare timestamps
3. compare authority
4. compare retailer/channel
5. compare geography
6. compare promotion conditions
7. determine same vs different commercial activity
8. send material unresolved conflicts to review

Never silently overwrite one source with another.

## 17. User Experience

Primary navigation:

```text
Overview
Promotions
Regional Pricing
Competitors
Sources
Review Queue
Settings
```

Key views include executive KPI dashboard, active promotion table, promotion detail drawer, regional price comparison, competitor comparison, source health, evidence viewer and review queue.

The UI reads production data through the API from PostgreSQL. It must not contain mock/fallback production promotion rows.

## 18. Scan vs Discover

`Scan now` = crawl active approved targets.

`Discover sources` = find candidate sources/URLs for assessment.

They are separate actions and separate operational jobs.

## 19. PostgreSQL Boundary

Use the existing PostgreSQL server with a dedicated project database:

```text
competitor_intel
```

and application schema:

```text
competitor_intel
```

The existing `dwh_prod` database is out of scope.

## 20. Success Criteria

The MVP is successful when:

1. At least one real source can be crawled end-to-end.
2. Additional sources can be registered without redesigning canonical tables.
3. Source URLs can be scheduled independently.
4. Real product/price/promotion observations reach PostgreSQL.
5. Evidence can be traced back to public source content.
6. Geography and regional price differences are preserved.
7. Expired promotions are excluded from Top 10.
8. Failed crawls do not erase valid historical data.
9. Duplicate observations from multiple sources can support one canonical activity.
10. Material conflicts enter review.
11. Dashboard/API/PostgreSQL show consistent data.
12. New source discovery can expand the source inventory without automatically trusting unassessed sources.
13. The system does not circumvent authentication, CAPTCHA, paywalls or access controls.

## 21. Implementation Priority

```text
1. Source + URL registry
2. Database migrations
3. Crawl/document persistence
4. One complete real source adapter
5. AI extraction + evidence
6. Validation + geography
7. Entity resolution + deduplication
8. Quality gate + Top 10
9. API
10. PostgreSQL-backed UI
11. More source adapters
12. Automated source discovery
13. Advanced regional analytics
```

Do not optimize dashboard appearance before the real-data vertical slice is reliable.
