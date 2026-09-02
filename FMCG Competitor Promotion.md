# PRD.md — FMCG Competitor Promotion Intelligence System

## 1. Product Overview

### Product Name

**Competitor Promotion Intelligence Platform**

### Objective

Build an AI-powered system that continuously monitors publicly available web sources to identify, extract, validate, normalize, and rank competitor marketing activities in the **FMCG biscuit, cracker, wafer, cookies, and related snack categories**.

The primary output is a PostgreSQL database containing structured competitor intelligence such as:

* Competitor / brand
* Product
* SKU / pack size
* Category
* Regular price
* Promotional price
* Discount percentage
* Promotion mechanism
* Buy 1 Get 1
* Buy 2 Get 1
* Buy X Get Y
* Multi-buy pricing
* Cashback
* Voucher
* Gift with purchase
* Member-only pricing
* Bundle promotion
* Minimum purchase requirement
* Promotion start date
* Promotion end date
* Retailer / channel
* Geography
* Source URL
* Source type
* Source reliability
* Evidence / extracted text
* AI confidence
* Last verified timestamp
* Promotion status

The system must identify the **Top 10 currently active competitor promotions**, prioritizing promotions that:

1. Are still valid.
2. Are highly relevant to biscuits/crackers.
3. Come from reliable sources.
4. Have strong evidence.
5. Have meaningful commercial impact.
6. Are recent.
7. Are not duplicates.

---

# 2. Business Problem

The marketing and commercial teams currently have limited visibility into competitor promotional activity.

Competitor promotions can appear across:

* Retailer websites
* E-commerce marketplaces
* Brand official stores
* Brand websites
* Digital catalogs
* Retailer catalogs
* Promotional landing pages
* Public social media
* News/media articles
* Promotional aggregators

The information is often:

* Unstructured
* Inconsistent
* Short-lived
* Duplicated
* Presented as images/PDFs
* Missing structured dates
* Missing regular prices
* Different across channels

A human team cannot efficiently monitor all of these sources continuously.

The proposed system automates this process.

---

# 3. Target Users

## Primary Users

### Marketing Team

Needs to understand:

* Who is promoting?
* Which brand/product?
* What promotion?
* How aggressive is the discount?
* Which retailer?
* When does it expire?

### Trade Marketing

Needs:

* Retailer-specific activity
* Promotion mechanics
* Price comparisons
* Competitor activity by channel
* Promotion intensity

### Brand / Category Manager

Needs:

* Competitive landscape
* Price positioning
* Promotion frequency
* Competitor strategy
* Category trends

### Sales Team

Needs:

* Current retailer promotions
* Competitor pricing
* Active trade promotions

### Management

Needs:

* Executive summary
* Top competitor activities
* Promotion intensity
* Competitor price movements

---

# 4. Product Scope

## Phase 1 — Indonesia

Focus on the Indonesian market.

Priority categories:

1. Biscuits
2. Crackers
3. Cookies
4. Wafer
5. Sandwich biscuits
6. Cream biscuits
7. Sweet biscuits
8. Savory crackers
9. Related snack products

Priority channels:

1. Indomaret
2. Alfamart
3. Superindo
4. Hypermart
5. Lotte Mart / Lotte Grosir
6. Yogya
7. TIP TOP
8. Transmart
9. Shopee
10. Tokopedia
11. Lazada
12. Brand official stores
13. Other reliable retailers

The architecture must allow additional countries, retailers and categories later.

---

# 5. Core Requirement

The system should answer:

> "What are the 10 most important biscuit/cracker competitor promotions that are active right now?"

Example output:

| Rank | Competitor   | Product      | Promotion   | Regular Price | Promo Price |         Saving | Retailer   | Valid Until |
| ---- | ------------ | ------------ | ----------- | ------------: | ----------: | -------------: | ---------- | ----------- |
| 1    | Competitor A | Cracker 200g | Buy 2 Get 1 |      Rp15,000 |    Rp15,000 |  33% effective | Retailer A | 10 Sep      |
| 2    | Competitor B | Biscuit 120g | 30% OFF     |      Rp10,000 |     Rp7,000 |            30% | Retailer B | 8 Sep       |
| 3    | Competitor C | Cookies 150g | Buy 1 Get 1 |      Rp20,000 |    Rp20,000 | ~50% effective | Online     | 15 Sep      |

The actual values must always come from source evidence rather than generated assumptions.

---

# 6. System Architecture

```text
                    WEB / PUBLIC SOURCES
                            |
                            v
                 +----------------------+
                 | Source Discovery     |
                 | Engine               |
                 +----------+-----------+
                            |
                            v
                 +----------------------+
                 | Web Crawlers /       |
                 | Search Collectors    |
                 +----------+-----------+
                            |
                            v
                 +----------------------+
                 | Raw Evidence Store   |
                 | HTML / PDF / Image   |
                 +----------+-----------+
                            |
                            v
                 +----------------------+
                 | Content Extraction   |
                 | OCR + Parser         |
                 +----------+-----------+
                            |
                            v
                 +----------------------+
                 | AI Promotion         |
                 | Extraction           |
                 +----------+-----------+
                            |
                            v
                 +----------------------+
                 | Validation Engine    |
                 | Date / Price /       |
                 | Promotion Validation |
                 +----------+-----------+
                            |
                            v
                 +----------------------+
                 | Entity Resolution    |
                 | Brand / Product / SKU|
                 +----------+-----------+
                            |
                            v
                 +----------------------+
                 | Deduplication Engine |
                 +----------+-----------+
                            |
                            v
                 +----------------------+
                 | Promotion Scoring    |
                 +----------+-----------+
                            |
                            v
                    POSTGRESQL
                            |
                +-----------+-----------+
                |                       |
                v                       v
        Top 10 API             Analytics / Dashboard
```

---

# 7. Data Collection Strategy

## 7.1 Do NOT rely on one scraping method

The system should use multiple collection methods.

### Method A — Search Engine Discovery

Use search engines to discover recent promotion pages.

Example queries:

```text
biskuit promo Indonesia
cracker promo Indonesia
biskuit diskon September 2026
cracker beli 1 gratis 1
biskuit beli 2 gratis 1
biskuit promo Indomaret
cracker promo Superindo
biskuit promo Alfamart
wafer promo Indonesia
```

Search queries should be dynamically generated.

Example:

```text
{category} + {promotion_keyword} + Indonesia
{brand} + promo
{retailer} + {category} + promo
```

---

# 8. Source Priority

The system must maintain a source reliability hierarchy.

## Tier 1 — Official Retailer / Brand Sources

Highest reliability.

Examples:

* Official retailer promotion pages
* Official retailer catalogs
* Official retailer e-commerce
* Official brand website
* Official brand store

Reliability score:

```text
1.00
```

---

## Tier 2 — Major E-commerce / Marketplace

Examples:

* Official brand stores
* Verified retailer stores
* Marketplace supermarket stores

Reliability:

```text
0.85 - 0.95
```

Important:

A marketplace product page is more reliable when the seller is clearly an official brand/retailer store.

---

## Tier 3 — Established Promotion / Retail Intelligence Sites

Examples:

* Promotion aggregators
* Retail catalog websites
* Established consumer media

Reliability:

```text
0.70 - 0.85
```

---

## Tier 4 — News / Media

Useful for discovery and confirmation.

Reliability:

```text
0.60 - 0.80
```

---

## Tier 5 — Social Media

Useful but potentially noisy.

Reliability:

```text
0.40 - 0.70
```

Social media should not automatically be treated as false, but should require stronger validation.

---

# 9. Source Registry

Create a configurable source table.

```sql
CREATE TABLE source_registry (
    id UUID PRIMARY KEY,
    source_name TEXT NOT NULL,
    domain TEXT NOT NULL,
    source_type TEXT,
    reliability_score NUMERIC(5,4),
    country TEXT,
    active BOOLEAN DEFAULT TRUE,
    crawl_frequency_minutes INTEGER,
    robots_allowed BOOLEAN,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

Example:

```text
Indomaret
Superindo
Lotte Grosir
Yogya
Official brand stores
Promotion aggregators
```

The crawler must never hard-code source behavior into the core application.

---

# 10. Crawling Frequency

Promotion intelligence is time-sensitive.

Recommended frequencies:

### High-priority retailer pages

Every:

```text
15–60 minutes
```

### Marketplace pages

Every:

```text
1–3 hours
```

### Promotion/catalog pages

Every:

```text
3–6 hours
```

### News/media

Every:

```text
6–12 hours
```

### Social sources

Every:

```text
6–24 hours
```

The system should support adaptive crawling.

If a promotion is near expiration:

```text
Increase crawl frequency
```

Example:

```text
Promotion expires in >7 days
    -> normal frequency

Promotion expires in 1–7 days
    -> increase frequency

Promotion expires in <24 hours
    -> high frequency
```

---

# 11. Raw Evidence Layer

Never directly write scraped information into the final promotion table.

First save the raw evidence.

```sql
CREATE TABLE crawl_documents (
    id UUID PRIMARY KEY,
    source_id UUID REFERENCES source_registry(id),
    url TEXT NOT NULL,
    canonical_url TEXT,
    title TEXT,
    content_type TEXT,
    raw_html TEXT,
    extracted_text TEXT,
    content_hash TEXT,
    published_at TIMESTAMPTZ,
    crawled_at TIMESTAMPTZ DEFAULT NOW(),
    http_status INTEGER,
    language TEXT,
    metadata JSONB
);
```

For images/PDFs:

```text
store:
- source URL
- file hash
- OCR text
- extraction metadata
```

Do not rely only on the current webpage because promotions may disappear after expiry.

---

# 12. AI Extraction

The AI should transform unstructured evidence into structured promotion data.

Input:

```text
URL
page title
page text
OCR text
publication date
crawl date
source metadata
```

Output:

```json
{
  "brand": "Roma",
  "manufacturer": "Mayora",
  "product_name": "Roma Malkist Crackers",
  "category": "cracker",
  "variant": "Abon",
  "pack_size": "105g",
  "regular_price": 7500,
  "promo_price": null,
  "currency": "IDR",
  "promotion_type": "BUY_X_GET_Y",
  "buy_quantity": 2,
  "free_quantity": 1,
  "discount_percentage": 33.33,
  "minimum_purchase": null,
  "promotion_start": "2026-06-25",
  "promotion_end": "2026-07-08",
  "retailer": "Indomaret",
  "channel": "offline_retail",
  "geography": "Indonesia",
  "confidence": 0.96,
  "evidence": "Beli 2 Gratis 1"
}
```

---

# 13. Promotion Taxonomy

The AI must normalize promotion language.

## Price Discount

Examples:

```text
20% OFF
Diskon 20%
Hemat 20%
Rp10.000 dari Rp12.500
```

Normalize to:

```text
DISCOUNT
```

---

## Buy One Get One

```text
Beli 1 Gratis 1
Buy 1 Get 1
B1G1
```

Normalize:

```text
BUY_X_GET_Y

buy_quantity = 1
free_quantity = 1
```

---

## Buy Two Get One

```text
Beli 2 Gratis 1
Buy 2 Get 1
B2G1
```

Normalize:

```text
BUY_X_GET_Y

buy_quantity = 2
free_quantity = 1
```

---

## Multi-buy

Examples:

```text
2 pcs Rp20.000
3 pcs Rp25.000
2 lebih hemat
```

Normalize:

```text
MULTIBUY
```

---

## Cashback

```text
Cashback Rp10.000
Cashback 20%
```

Normalize:

```text
CASHBACK
```

---

## Voucher

```text
Voucher Rp20.000
Diskon Rp10.000 dengan voucher
```

Normalize:

```text
VOUCHER
```

---

## Gift

```text
Gratis hadiah
Free gift
Hadiah langsung
```

Normalize:

```text
GIFT_WITH_PURCHASE
```

---

## Member Price

```text
Harga khusus member
Member discount
```

Normalize:

```text
MEMBER_PRICE
```

---

## Bundle

```text
Paket hemat
Bundle
Buy 3 products
```

Normalize:

```text
BUNDLE
```

---

# 14. PostgreSQL Data Model

Use a normalized relational model.

## Competitor

```sql
CREATE TABLE competitors (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    parent_company TEXT,
    country TEXT,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## Brands

```sql
CREATE TABLE brands (
    id UUID PRIMARY KEY,
    competitor_id UUID REFERENCES competitors(id),
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## Products

```sql
CREATE TABLE products (
    id UUID PRIMARY KEY,
    brand_id UUID REFERENCES brands(id),
    product_name TEXT NOT NULL,
    normalized_product_name TEXT,
    category TEXT,
    subcategory TEXT,
    variant TEXT,
    pack_size_value NUMERIC,
    pack_size_unit TEXT,
    sku TEXT,
    barcode TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

# 15. Retailers

```sql
CREATE TABLE retailers (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    normalized_name TEXT,
    channel_type TEXT,
    website TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

Example channel types:

```text
MODERN_TRADE
MINIMARKET
SUPERMARKET
HYPERMARKET
ECOMMERCE
MARKETPLACE
ONLINE_BRAND_STORE
```

---

# 16. Promotion Table

This is the primary business table.

```sql
CREATE TABLE promotions (
    id UUID PRIMARY KEY,

    competitor_id UUID REFERENCES competitors(id),
    brand_id UUID REFERENCES brands(id),
    product_id UUID REFERENCES products(id),
    retailer_id UUID REFERENCES retailers(id),

    promotion_type TEXT NOT NULL,

    promotion_title TEXT,

    regular_price NUMERIC(14,2),
    promo_price NUMERIC(14,2),
    currency TEXT DEFAULT 'IDR',

    discount_percentage NUMERIC(7,2),

    buy_quantity INTEGER,
    free_quantity INTEGER,

    minimum_purchase_quantity INTEGER,
    minimum_purchase_value NUMERIC(14,2),

    promotion_start TIMESTAMPTZ,
    promotion_end TIMESTAMPTZ,

    geography TEXT,
    channel TEXT,

    source_id UUID REFERENCES source_registry(id),
    source_document_id UUID REFERENCES crawl_documents(id),

    source_url TEXT NOT NULL,

    evidence_text TEXT,
    evidence_json JSONB,

    ai_confidence NUMERIC(5,4),
    source_reliability NUMERIC(5,4),

    status TEXT NOT NULL,

    first_seen_at TIMESTAMPTZ,
    last_seen_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

# 17. Promotion Status

Allowed values:

```text
DISCOVERED
VALIDATING
ACTIVE
EXPIRED
SUSPENDED
INVALID
UNKNOWN
```

The system must never classify a promotion as ACTIVE simply because it was found on a webpage.

---

# 18. Active Promotion Definition

A promotion is considered active when:

```text
promotion_start <= NOW()
AND
promotion_end >= NOW()
```

OR when the source explicitly states that it is currently active but no end date exists.

In that case:

```text
status = ACTIVE
end_date_confidence = LOW
```

The system must continue checking it.

---

# 19. Three-Month Rule

The user requirement is:

> Only show activities that are still valid and not more than 3 months old.

Implement two separate conditions.

### Condition A — Fresh Discovery

```sql
last_seen_at >= NOW() - INTERVAL '3 months'
```

### Condition B — Promotion Validity

```sql
promotion_end >= NOW()
```

For promotions without an explicit end date:

```text
last_seen_at >= NOW() - 7 days
```

should be required before considering them active.

This prevents an old evergreen product page from being incorrectly treated as an active promotion.

---

# 20. Promotion Validation Engine

Every extracted promotion goes through validation.

### Validation checks

#### Check 1 — Date

Does the source contain:

* Start date?
* End date?
* "Until..."
* "Berlaku..."
* "Period..."

#### Check 2 — Product

Does the source clearly identify the product?

#### Check 3 — Promotion

Is there explicit evidence of a promotion?

#### Check 4 — Price

If price exists:

```text
regular price
promo price
```

must be logically consistent.

Example:

```text
Regular = 10,000
Promo = 8,000
```

Expected:

```text
20% discount
```

#### Check 5 — Source

Is the source trusted?

#### Check 6 — Freshness

Was the page recently crawled?

---

# 21. Evidence Requirement

Every promotion must have evidence.

Example:

```json
{
  "evidence": [
    {
      "type": "TEXT",
      "content": "Beli 2 Gratis 1",
      "source_location": "promotion_description"
    },
    {
      "type": "PRICE",
      "content": "Rp10.500",
      "source_location": "product_card"
    },
    {
      "type": "DATE",
      "content": "6-19 August 2026",
      "source_location": "promotion_period"
    }
  ]
}
```

AI must not invent missing fields.

If the regular price is unavailable:

```text
regular_price = NULL
```

not an estimated value.

---

# 22. AI Confidence

AI must return confidence per extracted field.

Example:

```json
{
  "product_confidence": 0.98,
  "promotion_confidence": 0.99,
  "price_confidence": 0.96,
  "date_confidence": 0.91
}
```

Overall confidence:

```text
weighted average
```

Suggested weights:

```text
promotion = 30%
date = 25%
product = 20%
price = 15%
retailer = 10%
```

---

# 23. Entity Resolution

Different sources may write the same product differently.

Example:

```text
Roma Malkist Crackers 105g
Roma Malkist 105 gr
Roma Malkist Abon Gurih 105GR
ROMA MALKIST CRACKERS ABON 105G
```

AI/entity matching should map them to:

```text
product_id = XXXXX
```

Use a combination of:

1. Brand
2. Product name
3. Variant
4. Pack size
5. Barcode
6. Manufacturer
7. Semantic similarity

---

# 24. Deduplication

The same promotion may appear on:

* Retailer website
* News website
* Promotion aggregator
* Social media

These must not become four separate competitor promotions.

Create:

```sql
CREATE TABLE promotion_occurrences (
    id UUID PRIMARY KEY,
    promotion_id UUID REFERENCES promotions(id),
    source_document_id UUID REFERENCES crawl_documents(id),
    source_url TEXT,
    evidence_text TEXT,
    discovered_at TIMESTAMPTZ DEFAULT NOW()
);
```

One promotion:

```text
PROMOTION_ID = ABC
```

can have:

```text
Occurrence 1 -> Indomaret
Occurrence 2 -> Media article
Occurrence 3 -> Promotion aggregator
```

---

# 25. Deduplication Key

Initial deterministic key:

```text
brand
+
product
+
retailer
+
promotion_type
+
promotion_start
+
promotion_end
```

Then apply semantic matching.

Example:

```text
Roma Malkist
Beli 2 Gratis 1
Indomaret
25 Jun - 8 Jul
```

and:

```text
ROMA MALKIST CRACKERS
Buy 2 Get 1
Indomaret
25 June - 8 July
```

should become one promotion.

---

# 26. Promotion Impact Score

The system should rank promotions.

Create:

```text
promotion_score
```

Suggested formula:

```text
score =
    30% promotion_strength
  + 20% source_reliability
  + 15% freshness
  + 15% category_relevance
  + 10% competitor_importance
  + 10% evidence_confidence
```

---

# 27. Promotion Strength

Example scoring:

```text
BUY 1 GET 1       = 100
BUY 2 GET 1       = 90
BUY 3 GET 1       = 75
50% discount      = 95
40% discount      = 85
30% discount      = 75
20% discount      = 60
10% discount      = 40
Member-only       = 50
Cashback          = 40
Gift              = 40
Bundle            = 45
```

These values should be configurable.

---

# 28. Effective Discount Calculation

For:

```text
Buy 1 Get 1
```

effective discount:

```text
50%
```

For:

```text
Buy 2 Get 1
```

effective discount:

```text
33.33%
```

For:

```text
Buy 3 Get 1
```

effective discount:

```text
25%
```

Formula:

```text
effective_discount =
free_quantity
/
(buy_quantity + free_quantity)
* 100
```

However, only calculate this when the free item is equivalent or explicitly specified.

---

# 29. Top 10 Query

The application should expose a database view.

```sql
CREATE VIEW active_top_promotions AS

SELECT
    p.*,
    (
        p.ai_confidence
        * p.source_reliability
    ) AS confidence_score

FROM promotions p

WHERE
    p.status = 'ACTIVE'
    AND p.last_seen_at >= NOW() - INTERVAL '3 months'
    AND (
        p.promotion_end IS NULL
        OR p.promotion_end >= NOW()
    )

ORDER BY
    promotion_score DESC,
    last_seen_at DESC

LIMIT 10;
```

For production, use a materialized view or API-level ranking if ranking becomes computationally expensive.

---

# 30. Recommended API

Create:

```text
GET /api/v1/promotions/top10
```

Parameters:

```text
category
retailer
brand
competitor
channel
geography
promotion_type
days
```

Example:

```text
GET /api/v1/promotions/top10?category=cracker&days=90
```

Response:

```json
{
  "generated_at": "2026-09-02T10:00:00Z",
  "count": 10,
  "promotions": [
    {
      "rank": 1,
      "competitor": "Competitor A",
      "brand": "Brand A",
      "product": "Cracker 200g",
      "promotion_type": "BUY_X_GET_Y",
      "buy_quantity": 2,
      "free_quantity": 1,
      "regular_price": 15000,
      "promo_price": null,
      "effective_discount": 33.33,
      "retailer": "Retailer A",
      "valid_until": "2026-09-10",
      "confidence": 0.96,
      "source_url": "..."
    }
  ]
}
```

---

# 31. AI Agent Architecture

Use multiple specialized AI agents rather than one giant prompt.

## Agent 1 — Discovery Agent

Responsibilities:

* Generate search queries
* Discover URLs
* Find new sources
* Detect new promotion pages
* Expand source coverage

---

## Agent 2 — Extraction Agent

Responsibilities:

* Read HTML
* Read PDF
* Read OCR
* Extract products
* Extract prices
* Extract promotions
* Extract dates

---

## Agent 3 — Validation Agent

Responsibilities:

* Check promotion validity
* Check dates
* Check price consistency
* Check product relevance
* Reject hallucinated fields

---

## Agent 4 — Entity Resolution Agent

Responsibilities:

* Match competitor
* Match brand
* Match product
* Match SKU
* Normalize retailer

---

## Agent 5 — Deduplication Agent

Responsibilities:

* Identify same promotion across sources
* Merge evidence
* Select strongest source

---

## Agent 6 — Ranking Agent

Responsibilities:

* Calculate promotion strength
* Calculate commercial relevance
* Rank Top 10

---

# 32. AI Extraction Prompt Contract

The AI should be forced to return structured JSON.

Example schema:

```json
{
  "is_relevant": true,
  "competitor": {
    "name": "",
    "confidence": 0.0
  },
  "brand": {
    "name": "",
    "confidence": 0.0
  },
  "product": {
    "name": "",
    "variant": "",
    "pack_size": "",
    "category": "",
    "confidence": 0.0
  },
  "promotion": {
    "type": "",
    "title": "",
    "buy_quantity": null,
    "free_quantity": null,
    "discount_percentage": null,
    "regular_price": null,
    "promo_price": null,
    "confidence": 0.0
  },
  "validity": {
    "start": null,
    "end": null,
    "confidence": 0.0
  },
  "retailer": {
    "name": "",
    "confidence": 0.0
  },
  "evidence": [],
  "overall_confidence": 0.0
}
```

Rules:

```text
1. Never invent missing values.
2. Return null when information is unavailable.
3. Preserve original currency.
4. Preserve original promotion wording in evidence.
5. Normalize promotion_type.
6. Only classify as relevant when the product belongs to target categories.
7. Dates must be ISO-8601.
8. Prices must be numeric.
9. Every important extracted field must have evidence.
10. Distinguish promotion date from article publication date.
```

---

# 33. Web Scraping Strategy

Use a hybrid architecture.

### Static HTML

Use:

```text
HTTP client
HTML parser
```

### JavaScript websites

Use:

```text
Headless browser
```

### PDF catalogs

Use:

```text
PDF parser
OCR if required
```

### Image promotions

Use:

```text
OCR
Vision AI
```

### Search

Use:

```text
Search API
```

Do not build a crawler that attempts to crawl the entire internet.

Start with a controlled source registry and use search discovery to expand coverage.

---

# 34. Robots.txt and Compliance

The system must:

* Respect robots.txt where applicable.
* Respect website terms.
* Use reasonable crawl rates.
* Avoid bypassing authentication.
* Avoid CAPTCHA bypass.
* Avoid scraping private/non-public data.
* Only collect publicly available information.
* Store source URLs.
* Identify crawl timestamps.

The system should favor official APIs or permitted feeds when available.

---

# 35. Data Freshness

Each promotion must contain:

```text
first_seen_at
last_seen_at
last_validated_at
promotion_start
promotion_end
```

Example:

```text
First seen:
2026-08-20

Last validated:
2026-09-02 16:30

Promotion ends:
2026-09-10
```

This allows the system to know that the promotion is still being observed.

---

# 36. Expiration Worker

Run a scheduled worker:

```text
every 15 minutes
```

Logic:

```python
if promotion_end < now:
    status = "EXPIRED"
```

For promotions without an explicit end date:

```text
if last_seen_at > threshold:
    status = "UNKNOWN"
```

Never leave stale promotions permanently ACTIVE.

---

# 37. Source Reliability Updating

Source reliability should improve or decrease based on historical accuracy.

Example:

```text
Initial source reliability = 0.80
```

If source consistently publishes accurate active promotions:

```text
0.80 -> 0.90
```

If source frequently has expired information:

```text
0.80 -> 0.65
```

Create:

```sql
CREATE TABLE source_quality_metrics (
    id UUID PRIMARY KEY,
    source_id UUID REFERENCES source_registry(id),
    total_promotions INTEGER,
    verified_promotions INTEGER,
    expired_false_positive_count INTEGER,
    accuracy_score NUMERIC(5,4),
    calculated_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

# 38. Observability

The system must monitor:

### Crawl metrics

```text
pages crawled
pages failed
HTTP errors
crawl duration
```

### AI metrics

```text
documents processed
extractions successful
extraction failures
average confidence
```

### Business metrics

```text
active promotions
expired promotions
new promotions/day
promotions by competitor
promotions by retailer
promotions by type
```

---

# 39. Error Handling

If crawling fails:

```text
retry with exponential backoff
```

If AI extraction fails:

```text
retry
```

If validation fails:

```text
status = UNKNOWN
```

If source disappears:

```text
do not immediately expire promotion
```

Instead:

```text
mark source_unavailable
```

Then rely on the next validation cycle.

---

# 40. Recommended Technology Stack

## Backend

Recommended:

```text
Python
FastAPI
```

## Crawling

```text
Playwright
httpx
BeautifulSoup
Trafilatura
```

## PDF

```text
PyMuPDF
```

## OCR

Use a reliable OCR provider or local OCR depending on cost/quality requirements.

## AI

Use an LLM capable of:

* Structured JSON output
* Long-context extraction
* Vision/OCR interpretation
* Entity matching

## Database

```text
PostgreSQL
```

Recommended extensions:

```text
pgvector
pg_trgm
```

`pgvector` can support semantic product matching.

`pg_trgm` can support fuzzy text matching.

## Queue

```text
Redis
Celery
```

or:

```text
RabbitMQ
```

## Scheduler

```text
Celery Beat
```

or:

```text
APScheduler
```

## Deployment

Initial:

```text
Docker
```

Production:

```text
Kubernetes
```

if scale requires it.

---

# 41. Recommended Database Indexes

```sql
CREATE INDEX idx_promotions_status
ON promotions(status);

CREATE INDEX idx_promotions_end
ON promotions(promotion_end);

CREATE INDEX idx_promotions_last_seen
ON promotions(last_seen_at);

CREATE INDEX idx_promotions_brand
ON promotions(brand_id);

CREATE INDEX idx_promotions_product
ON promotions(product_id);

CREATE INDEX idx_promotions_retailer
ON promotions(retailer_id);

CREATE INDEX idx_promotions_type
ON promotions(promotion_type);

CREATE INDEX idx_promotions_active
ON promotions(status, promotion_end, last_seen_at);
```

For fuzzy product matching:

```sql
CREATE INDEX idx_products_name_trgm
ON products
USING gin(normalized_product_name gin_trgm_ops);
```

---

# 42. Dashboard Requirements

The first dashboard should contain:

## KPI Cards

```text
Active Promotions
Competitors Tracked
Brands Tracked
Retailers Tracked
Promotions Today
Promotions Expiring < 7 Days
```

## Top 10 Promotion Table

Columns:

```text
Rank
Competitor
Brand
Product
Category
Promotion
Regular Price
Promo Price
Effective Discount
Retailer
Start
End
Confidence
Source
```

## Filters

```text
Date
Competitor
Brand
Retailer
Category
Promotion Type
Channel
Discount Range
```

---

# 43. Additional Analytics

After MVP, support:

### Competitor Promotion Frequency

```text
Competitor A -> 32 promotions
Competitor B -> 21 promotions
Competitor C -> 17 promotions
```

### Promotion Type Distribution

```text
Discount       45%
Buy X Get Y    25%
Bundle         12%
Member Price   10%
Gift            5%
Other           3%
```

### Price Index

Compare competitor product prices.

```text
Our product
vs
Competitor A
vs
Competitor B
```

### Promotion Intensity

Calculate:

```text
promotion_count
+
average_discount
+
promotion_frequency
```

per competitor.

---

# 44. Alerting

The system should eventually support alerts.

Examples:

```text
Competitor launches >30% discount
```

```text
Competitor launches B1G1
```

```text
Competitor promotion detected in key retailer
```

```text
Competitor price drops >15%
```

```text
New promotion from top competitor
```

```text
Promotion expires within 24 hours
```

Delivery:

```text
Email
Slack
Microsoft Teams
Dashboard
Webhook
```

---

# 45. Example Alert

```text
🚨 COMPETITOR PROMOTION ALERT

Competitor:
Competitor A

Brand:
Brand A

Product:
Cracker Original 200g

Retailer:
Indomaret

Promotion:
BUY 2 GET 1

Effective Discount:
33.3%

Valid:
2 Sep – 15 Sep 2026

Source Reliability:
0.98

AI Confidence:
0.96

Promotion Score:
91.4

Source:
[URL]
```

---

# 46. MVP Scope

Do NOT build everything initially.

## MVP Phase 1

Track:

```text
5–8 major Indonesian retailers
```

Categories:

```text
Biscuit
Cracker
Wafer
Cookies
```

Promotion types:

```text
Discount
Buy X Get Y
Multibuy
Member Price
Bundle
Gift
Cashback
Voucher
```

Sources:

```text
Official retailer websites
Official retailer catalogs
Reliable promotion aggregators
Official marketplace stores
```

Output:

```text
PostgreSQL
Top 10 API
Basic dashboard
```

---

# 47. MVP Success Criteria

The MVP is successful if:

### Coverage

At least:

```text
100+ relevant promotion observations/week
```

from the selected sources.

### Accuracy

Target:

```text
>90% promotion classification accuracy
```

### Date accuracy

Target:

```text
>95%
```

### Product relevance

Target:

```text
>95%
```

### False active promotions

Target:

```text
<5%
```

### Deduplication

Target:

```text
>90% duplicate reduction
```

---

# 48. Development Roadmap

## Sprint 1 — Foundation

Build:

```text
PostgreSQL schema
Source registry
Crawler framework
Raw document storage
```

Deliverable:

```text
Raw web evidence stored in database/object storage
```

---

## Sprint 2 — Extraction

Build:

```text
HTML extraction
PDF extraction
OCR pipeline
AI extraction
Structured JSON
```

Deliverable:

```text
Raw page -> structured promotion
```

---

## Sprint 3 — Validation

Build:

```text
Date validator
Price validator
Promotion validator
Confidence scoring
```

Deliverable:

```text
Structured promotion -> validated promotion
```

---

## Sprint 4 — Entity Resolution

Build:

```text
Brand matching
Product matching
Retailer matching
Competitor matching
Deduplication
```

Deliverable:

```text
Clean promotion database
```

---

## Sprint 5 — Ranking

Build:

```text
Promotion score
Source score
Freshness score
Commercial impact score
Top 10 algorithm
```

Deliverable:

```text
Top 10 active competitor promotions
```

---

## Sprint 6 — API + Dashboard

Build:

```text
REST API
Dashboard
Filters
Top 10 view
Promotion detail
Source evidence
```

---

## Sprint 7 — Alerting

Build:

```text
New promotion alerts
Large discount alerts
B1G1 alerts
Expiring promotion alerts
```

---

# 49. Production Architecture

Recommended final architecture:

```text
                         +----------------+
                         | Search Engine  |
                         +-------+--------+
                                 |
                         +-------v--------+
                         | Discovery      |
                         | Agent          |
                         +-------+--------+
                                 |
                +----------------v----------------+
                |         Crawl Queue            |
                +----------------+----------------+
                                 |
             +-------------------+-------------------+
             |                   |                   |
       +-----v-----+       +-----v-----+       +-----v-----+
       | HTML      |       | PDF       |       | Browser   |
       | Crawler   |       | Crawler   |       | Crawler   |
       +-----+-----+       +-----+-----+       +-----+-----+
             |                   |                   |
             +-------------------+-------------------+
                                 |
                         +-------v--------+
                         | Raw Evidence   |
                         +-------+--------+
                                 |
                         +-------v--------+
                         | OCR / Parser   |
                         +-------+--------+
                                 |
                         +-------v--------+
                         | AI Extraction  |
                         +-------+--------+
                                 |
                         +-------v--------+
                         | Validation     |
                         +-------+--------+
                                 |
                         +-------v--------+
                         | Entity         |
                         | Resolution     |
                         +-------+--------+
                                 |
                         +-------v--------+
                         | Deduplication  |
                         +-------+--------+
                                 |
                         +-------v--------+
                         | Scoring        |
                         +-------+--------+
                                 |
                         +-------v--------+
                         | PostgreSQL     |
                         +-------+--------+
                                 |
                 +---------------+---------------+
                 |               |               |
          +------v------+ +------v------+ +------v------+
          | REST API    | | Dashboard   | | Alerting    |
          +-------------+ +-------------+ +-------------+
```

---

# 50. Important Design Principle

The most important architectural principle is:

```text
SOURCE
  ↓
RAW EVIDENCE
  ↓
AI EXTRACTION
  ↓
VALIDATION
  ↓
ENTITY RESOLUTION
  ↓
DEDUPLICATION
  ↓
SCORING
  ↓
ACTIVE PROMOTION
```

Do not build:

```text
SOURCE
  ↓
LLM
  ↓
DATABASE
```

because this will create:

* Hallucinated prices
* Incorrect dates
* Duplicate promotions
* Expired promotions
* Incorrect product matching
* Poor auditability

---

# 51. Auditability Requirement

Every database promotion must be explainable.

For any promotion, a user should be able to answer:

```text
Where did this information come from?
When was it found?
When was it last checked?
What exactly did the source say?
Why does the AI believe it is a promotion?
Why is it still active?
Why is it ranked Top 10?
```

Therefore the database must retain:

```text
source URL
crawl timestamp
raw evidence
extracted evidence
AI confidence
validation result
ranking score
```

---

# 52. Future Features

After the MVP:

### Competitive Price Intelligence

Track:

```text
price history
price changes
price per 100g
price index
```

### Promotion History

Example:

```text
Brand A

Jan: 20% OFF
Feb: B2G1
Mar: 30% OFF
Apr: Member Price
May: B1G1
```

This allows detection of promotional strategy.

### Competitor Strategy Detection

AI can classify:

```text
Aggressive discounting
Frequent multibuy
Premium positioning
Retailer-specific strategy
Seasonal strategy
```

### Predictive Intelligence

Eventually:

```text
"What promotion is competitor likely to launch next?"
```

based on historical patterns.

---

# 53. Final Definition of Done

The project is considered production-ready when:

* [ ] Source registry exists.
* [ ] Crawlers operate automatically.
* [ ] Raw evidence is retained.
* [ ] PDF/image promotions can be processed.
* [ ] AI extracts structured promotion data.
* [ ] AI never invents missing values.
* [ ] Promotion dates are validated.
* [ ] Expired promotions are automatically removed from active results.
* [ ] Products are mapped to normalized entities.
* [ ] Duplicate promotions are merged.
* [ ] Source reliability is scored.
* [ ] AI confidence is stored.
* [ ] Promotion strength is calculated.
* [ ] Top 10 ranking is available.
* [ ] PostgreSQL contains the canonical data.
* [ ] API exposes active promotions.
* [ ] Dashboard displays the Top 10.
* [ ] Source evidence is accessible.
* [ ] Alerts can be generated.
* [ ] Crawl and AI failures are observable.
* [ ] System respects website access policies.
* [ ] Historical promotion data is retained.

---

# 54. Recommended First Deliverable

The engineering team should build the following first:

```text
1. PostgreSQL schema
2. Source registry
3. 5 initial retailer sources
4. Search discovery service
5. Web crawler
6. Raw evidence store
7. AI extraction service
8. Promotion validation service
9. Product/brand entity matching
10. Deduplication
11. Promotion scoring
12. Top 10 API
13. Simple dashboard
14. Scheduled crawling
15. Expiration worker
```

The first production question the system must answer reliably is:

> "Show me the 10 strongest active biscuit/cracker competitor promotions in Indonesia right now, with product, retailer, price, promotion mechanic, validity, confidence, and source evidence."

That should be the **MVP acceptance criterion**.
