# TECHNICAL_DESIGN.md

# Competitor Promotion Intelligence Platform

## 1. Purpose

This document defines the technical architecture and implementation requirements for the **Competitor Promotion Intelligence Platform**.

The platform continuously discovers, crawls, extracts, validates, normalizes, deduplicates, and ranks competitor marketing promotions for FMCG products, with an initial focus on:

* Biscuits
* Crackers
* Cookies
* Wafers
* Similar snack products

The system should identify currently valid competitor activities such as:

* Buy 1 Get 1
* Buy 2 Get 1
* Buy X Get Y
* Percentage discounts
* Fixed-price discounts
* Multi-buy promotions
* Bundle promotions
* Member prices
* Cashback
* Vouchers
* Gifts with purchase
* Minimum-spend promotions
* Other commercially relevant promotional mechanics

The primary output is a ranked list of the **Top 10 currently active competitor promotions**.

---

# 2. Critical Database Architecture Decision

## 2.1 Existing PostgreSQL Server Will Be Reused

The project will **not deploy a new PostgreSQL server** and will **not run PostgreSQL inside Docker**.

The existing PostgreSQL server will be reused.

However, the project must create a **new dedicated PostgreSQL database**:

```text
competitor_intel
```

This database must initially be empty and populated exclusively by this project.

The existing database:

```text
dwh_prod
```

is completely outside the scope of this application.

---

## 2.2 Database Isolation Requirement

The application must never connect to `dwh_prod`.

The application must receive credentials that can connect only to:

```text
competitor_intel
```

Recommended PostgreSQL structure:

```text
Existing PostgreSQL Server
│
├── dwh_prod
│   └── Existing DWH
│
├── competitor_intel
│   └── competitor_intel schema
│       ├── source_registry
│       ├── crawl_jobs
│       ├── crawl_documents
│       ├── promotion_observations
│       ├── promotions
│       ├── promotion_evidence
│       ├── competitors
│       ├── brands
│       ├── products
│       ├── retailers
│       ├── entity_mapping
│       ├── review_queue
│       └── ...
│
└── Other existing databases
```

This database-level separation is a mandatory security and implementation boundary.

---

# 3. Explicit Non-Goals

The MVP must NOT:

* Modify `dwh_prod`
* Create tables in `dwh_prod`
* Alter tables in `dwh_prod`
* Read data from `dwh_prod`
* Require access credentials to `dwh_prod`
* Inspect the existing DWH schema
* Create foreign keys across databases
* Depend on existing DWH tables
* Assume any existing project-specific tables
* Reuse existing DWH business logic
* Require PostgreSQL to run inside Docker

There must be no implementation step called:

```text
inspect_dwh.py
```

and no requirement to generate a:

```text
DWH_SCHEMA_MAPPING.md
```

The Competitor Intelligence database must be designed independently from the DWH.

---

# 4. Infrastructure Architecture

## 4.1 High-Level Architecture

```text
                         PUBLIC WEB
                             │
              ┌──────────────┴──────────────┐
              │                             │
        Retailer Websites             Brand Websites
              │                             │
        Marketplaces                    Promo Pages
              │                             │
              └──────────────┬──────────────┘
                             │
                     Source Discovery
                             │
                         Crawler
                             │
                    Raw Document Store
                             │
                  HTML / PDF / Image / Text
                             │
                      Content Extraction
                             │
                         OCR / Parser
                             │
                     AI Promotion Extraction
                             │
                     Validation & Normalization
                             │
                      Entity Resolution
                             │
                        Deduplication
                             │
                        Ranking Engine
                             │
                  PostgreSQL: competitor_intel
                             │
                  ┌──────────┴──────────┐
                  │                     │
              REST API             Dashboard
                  │
              Top 10 Promotions
```

---

# 5. Runtime Components

The application should consist of the following logical components:

```text
competitor-intel/
│
├── API
├── Scheduler
├── Source Discovery
├── Crawler
├── Document Processor
├── OCR Processor
├── AI Extraction
├── Validation
├── Entity Resolution
├── Deduplication
├── Ranking
├── Alerting
└── Database
```

Recommended technology stack:

| Component          | Technology                                   |
| ------------------ | -------------------------------------------- |
| Language           | Python 3.12+                                 |
| API                | FastAPI                                      |
| Validation         | Pydantic                                     |
| ORM                | SQLAlchemy 2                                 |
| PostgreSQL driver  | psycopg3                                     |
| HTTP client        | httpx                                        |
| HTML parsing       | BeautifulSoup                                |
| Content extraction | trafilatura                                  |
| Browser automation | Playwright                                   |
| PDF extraction     | PyMuPDF                                      |
| OCR                | Tesseract or equivalent                      |
| AI                 | LLM with structured JSON / vision capability |
| Database           | Existing PostgreSQL server                   |
| Search             | PostgreSQL + pg_trgm                         |
| Vector search      | pgvector, optional                           |
| Background jobs    | Celery or equivalent                         |
| Queue/cache        | Redis, optional                              |
| Object storage     | S3-compatible storage or local storage       |
| Containers         | Docker for application services only         |
| Deployment         | Docker Compose initially                     |

---

# 6. PostgreSQL Provisioning

## 6.1 Database

Create a new database:

```sql
CREATE DATABASE competitor_intel;
```

Do not create any application tables in `dwh_prod`.

---

## 6.2 Dedicated Database Owner

Create a dedicated owner:

```sql
CREATE ROLE competitor_intel_owner
WITH LOGIN
PASSWORD '<STRONG_PASSWORD>';
```

Then:

```sql
ALTER DATABASE competitor_intel
OWNER TO competitor_intel_owner;
```

The actual production password must be stored in a secret manager or environment configuration, never committed to Git.

---

## 6.3 Application Role

Create a separate application role:

```sql
CREATE ROLE competitor_intel_app
WITH LOGIN
PASSWORD '<STRONG_PASSWORD>';
```

Grant access only to the new database:

```sql
GRANT CONNECT ON DATABASE competitor_intel
TO competitor_intel_app;
```

The application role must not receive:

```sql
CONNECT ON DATABASE dwh_prod
```

or any equivalent access.

---

# 7. PostgreSQL Schema

Inside `competitor_intel`, create:

```sql
CREATE SCHEMA competitor_intel;
```

Recommended extensions:

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

Optionally:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

`pgvector` should only be enabled if semantic similarity is implemented.

---

# 8. Application Database URL

The application must use an environment variable.

Example:

```env
DATABASE_URL=postgresql+psycopg://competitor_intel_app:<PASSWORD>@<POSTGRES_HOST>:5432/competitor_intel
```

Additional environment variables:

```env
POSTGRES_HOST=
POSTGRES_PORT=5432
POSTGRES_DB=competitor_intel
POSTGRES_USER=competitor_intel_app
POSTGRES_PASSWORD=

DATABASE_SCHEMA=competitor_intel
```

Never hard-code database credentials.

Never provide `dwh_prod` credentials to the application.

---

# 9. Migration Strategy

The project must use database migrations.

Recommended:

```text
Alembic
```

Migration flow:

```text
Fresh competitor_intel database
            │
            ▼
       Alembic upgrade
            │
            ▼
      Empty application schema
            │
            ▼
       Seed base data
```

The first migration should create the complete MVP schema.

A developer must be able to provision a new environment with:

```bash
alembic upgrade head
```

without depending on any existing database tables.

---

# 10. Database Model

The database should contain the following major entities.

```text
source_registry
crawl_jobs
crawl_documents
promotion_observations
promotions
promotion_evidence
competitors
brands
products
retailers
entity_mapping
review_queue
```

Additional supporting tables may be introduced where necessary.

---

# 11. source_registry

Stores known sources that the crawler monitors.

Suggested columns:

```text
id
name
base_url
source_type
tier
country
language
category
crawl_frequency_minutes
priority
is_active
robots_allowed
last_crawled_at
last_success_at
last_error_at
created_at
updated_at
```

Source types:

```text
RETAILER
BRAND
MARKETPLACE
PROMOTION_AGGREGATOR
NEWS
SOCIAL
OTHER
```

Source reliability tiers:

```text
TIER_1
TIER_2
TIER_3
TIER_4
TIER_5
```

Recommended interpretation:

### Tier 1

Official retailer and official brand sources.

### Tier 2

Official marketplace stores and established marketplace promotion pages.

### Tier 3

Promotion aggregators.

### Tier 4

News and media.

### Tier 5

Social media and other secondary sources.

---

# 12. crawl_jobs

Tracks individual crawl attempts.

Suggested columns:

```text
id
source_id
url
job_type
status
started_at
completed_at
http_status
error_message
retry_count
content_hash
created_at
```

Statuses:

```text
QUEUED
RUNNING
SUCCESS
FAILED
SKIPPED
BLOCKED
```

---

# 13. crawl_documents

Stores normalized metadata about retrieved documents.

Suggested columns:

```text
id
crawl_job_id
source_id
url
canonical_url
document_type
title
raw_content_uri
text_content
content_hash
published_at
retrieved_at
language
http_status
created_at
```

Document types:

```text
HTML
PDF
IMAGE
JSON
TEXT
OTHER
```

Large raw files should preferably be stored in object storage.

PostgreSQL should store the URI and metadata rather than unnecessarily storing large binary objects.

---

# 14. promotion_observations

This table represents what the crawler/AI observed from a specific source at a specific time.

This is important because the same promotion may change over time.

Suggested columns:

```text
id
document_id
extraction_run_id
raw_text
raw_evidence
extracted_json
ai_confidence
observed_at
created_at
```

This table should preserve the original observation independently from the canonical promotion record.

---

# 15. promotions

This is the primary canonical promotion table.

Suggested columns:

```text
id

competitor_id
retailer_id
brand_id
product_id

product_name
sku
pack_size
category

regular_price
promo_price
currency

discount_percentage

promotion_type

buy_quantity
free_quantity

bundle_quantity

cashback_amount
voucher_amount

minimum_purchase_amount
minimum_purchase_quantity

gift_description

promotion_title
promotion_description

start_date
end_date

channel
geography

status

source_reliability
ai_confidence

first_seen_at
last_seen_at

created_at
updated_at
```

---

# 16. Promotion Types

The system must use a controlled taxonomy.

```text
DISCOUNT
BUY_X_GET_Y
MULTIBUY
CASHBACK
VOUCHER
MEMBER_PRICE
GIFT_WITH_PURCHASE
BUNDLE
MINIMUM_SPEND
OTHER
```

The system may add more promotion types later without breaking existing records.

---

# 17. Promotion Status

Allowed statuses:

```text
ACTIVE
EXPIRED
UPCOMING
UNKNOWN
REVIEW_REQUIRED
```

A promotion is considered active when:

```text
start_date <= current_timestamp
AND
(
    end_date >= current_timestamp
    OR
    end_date IS NULL
)
```

However, promotions with no explicit end date require recent verification.

Recommended rule:

```text
end_date IS NULL
AND
last_seen_at >= current_timestamp - interval '7 days'
```

Otherwise the promotion should not automatically appear in the Top 10.

---

# 18. Three-Month Recency Rule

The Top 10 must contain promotions that are:

1. Relevant to the target category
2. Active
3. Recent
4. Supported by reliable evidence

A promotion is considered recent when:

```sql
last_seen_at >= NOW() - INTERVAL '3 months'
```

The preferred interpretation is:

> A promotion must currently be valid and must have been observed within the last three months.

Promotions older than three months must not appear in the default Top 10.

---

# 19. Promotion Evidence

Every promotion extracted by AI must have supporting evidence.

Suggested table:

```text
promotion_evidence
```

Columns:

```text
id
promotion_id
document_id

evidence_type
evidence_text

source_url
page_number
image_uri

captured_at
created_at
```

Evidence types:

```text
TEXT
TABLE
IMAGE
OCR
PRICE
PROMOTION_BADGE
DATE
OTHER
```

A promotion should not be considered high confidence without supporting evidence.

---

# 20. Competitors

Suggested table:

```text
competitors
```

Columns:

```text
id
name
normalized_name
website
importance_score
is_active
created_at
updated_at
```

`importance_score` can be used by the ranking engine to prioritize strategically important competitors.

---

# 21. Brands

Suggested table:

```text
brands
```

Columns:

```text
id
competitor_id
name
normalized_name
manufacturer
created_at
updated_at
```

---

# 22. Products

Suggested table:

```text
products
```

Columns:

```text
id
brand_id
name
normalized_name
sku
barcode
variant
pack_size
unit
category
subcategory
created_at
updated_at
```

The system must support products without known SKU or barcode.

Unknown values must remain `NULL`.

The AI must never invent a SKU, barcode, price, or promotion date.

---

# 23. Retailers

Suggested table:

```text
retailers
```

Columns:

```text
id
name
normalized_name
website
channel
country
created_at
updated_at
```

Example channels:

```text
SUPERMARKET
MINIMARKET
E_COMMERCE
MARKETPLACE
OFFICIAL_STORE
OTHER
```

---

# 24. Entity Mapping

The system must resolve extracted entities to canonical entities.

Suggested table:

```text
entity_mapping
```

Columns:

```text
id
entity_type
source_value
canonical_entity_id
match_method
confidence
created_at
updated_at
```

Match methods:

```text
EXACT
NORMALIZED_EXACT
SKU
BARCODE
FUZZY
SEMANTIC
AI
MANUAL
```

---

# 25. Review Queue

Low-confidence or ambiguous records should be routed to:

```text
review_queue
```

Suggested columns:

```text
id
entity_type
entity_id
reason
priority
status
assigned_to
created_at
reviewed_at
review_notes
```

Statuses:

```text
PENDING
IN_REVIEW
APPROVED
REJECTED
```

---

# 26. AI Extraction

The AI extraction layer converts unstructured web content into structured promotion data.

Input:

```text
HTML
PDF
Image
OCR text
Plain text
Marketplace content
Retailer catalog
Promotion page
```

Output must conform to a strict schema.

Example:

```json
{
  "competitor": null,
  "retailer": null,
  "brand": null,
  "product": null,
  "sku": null,
  "pack_size": null,
  "category": null,
  "regular_price": null,
  "promo_price": null,
  "discount_percentage": null,
  "promotion_type": "BUY_X_GET_Y",
  "buy_quantity": 2,
  "free_quantity": 1,
  "start_date": null,
  "end_date": null,
  "minimum_purchase_quantity": null,
  "minimum_purchase_amount": null,
  "gift_description": null,
  "source_url": null,
  "evidence": [],
  "confidence": 0.0
}
```

---

# 27. AI Extraction Rules

The AI must follow these rules:

### Rule 1 — Never invent

If a value is not present:

```text
NULL
```

must be returned.

### Rule 2 — Evidence required

Each important extracted field should have evidence where practical.

### Rule 3 — Preserve source wording

The original promotion wording should be preserved.

### Rule 4 — Normalize separately

Do not destroy the original evidence during normalization.

### Rule 5 — Dates

If only a date range is present, normalize it.

If no date is available, do not invent one.

### Rule 6 — Prices

Preserve:

* Original price
* Promotional price
* Currency
* Unit/pack context

### Rule 7 — Promotion mechanism

Explicitly identify whether the activity is:

```text
DISCOUNT
BUY_X_GET_Y
MULTIBUY
CASHBACK
VOUCHER
MEMBER_PRICE
GIFT_WITH_PURCHASE
BUNDLE
MINIMUM_SPEND
OTHER
```

---

# 28. Buy X Get Y Normalization

For example:

```text
Buy 1 Get 1
```

becomes:

```text
buy_quantity = 1
free_quantity = 1
```

```text
Buy 2 Get 1
```

becomes:

```text
buy_quantity = 2
free_quantity = 1
```

```text
Buy 3 Get 1
```

becomes:

```text
buy_quantity = 3
free_quantity = 1
```

---

# 29. Effective Promotion Strength

For equivalent free products:

```text
effective_discount =
free_quantity /
(buy_quantity + free_quantity)
* 100
```

Examples:

```text
B1G1 = 50%
B2G1 = 33.33%
B3G1 = 25%
```

This normalized value can be used by the ranking engine.

It must not replace the original promotion wording.

---

# 30. Discount Normalization

For percentage discounts:

```text
discount_percentage =
(
    regular_price - promo_price
)
/
regular_price
* 100
```

The system should retain the retailer's stated discount when explicitly available and may calculate a normalized discount for comparison.

---

# 31. Bundle Normalization

Bundle promotions should retain:

```text
bundle_quantity
bundle_price
regular_total_price
discount_percentage
bundle_description
```

Example:

```text
3 packs for Rp25,000
```

must not automatically be interpreted as B2G1 unless the source explicitly states that mechanism.

---

# 32. Source Discovery

The source discovery system should identify:

* Retailer promotion pages
* Brand promotion pages
* E-commerce stores
* Marketplace stores
* Digital catalogs
* Promotional PDFs
* Weekly flyers
* Product pages
* News articles
* Promotion aggregators

Discovery methods may include:

```text
Search engines
Known source registry
Sitemaps
Internal site links
RSS feeds
Marketplace category pages
Retailer promotion pages
```

---

# 33. Crawler

The crawler must support:

### Static HTML

Use:

```text
httpx
BeautifulSoup
trafilatura
```

### JavaScript-heavy pages

Use:

```text
Playwright
```

### PDF

Use:

```text
PyMuPDF
```

### Images

Use OCR.

### Structured data

Extract:

```text
JSON-LD
OpenGraph
Product schema
Price schema
```

where available.

---

# 34. Crawl Scheduling

Recommended initial schedules:

| Source                       |  Frequency |
| ---------------------------- | ---------: |
| High-priority promotion page |  15–60 min |
| Marketplace                  |  1–3 hours |
| Retailer catalog             |  3–6 hours |
| Brand promotion page         |  3–6 hours |
| News/media                   | 6–12 hours |
| Social                       | 6–24 hours |

The scheduler should eventually become adaptive.

For example:

```text
Promotion expires in 2 hours
        ↓
Increase crawl frequency
        ↓
Promotion expires
        ↓
Mark EXPIRED
```

---

# 35. Crawl Reliability

The crawler must implement:

* Retry
* Exponential backoff
* Timeout
* Rate limiting
* User-agent management
* Duplicate URL prevention
* Content hashing
* HTTP status handling
* robots.txt compliance where applicable
* Crawl logging
* Error classification

Potential errors:

```text
TIMEOUT
DNS_ERROR
HTTP_403
HTTP_404
HTTP_429
SERVER_ERROR
PARSER_ERROR
OCR_ERROR
AI_ERROR
UNKNOWN
```

---

# 36. Deduplication

The same promotion can appear on:

* Retailer website
* Retailer PDF
* News article
* Promotion aggregator
* Marketplace
* Social post

The system must avoid showing duplicates in the Top 10.

Deduplication should use multiple layers.

## Layer 1 — Deterministic

Potential key:

```text
competitor
retailer
product
promotion_type
start_date
end_date
promotion_mechanism
```

## Layer 2 — Fuzzy matching

Use:

```text
pg_trgm
```

for product/promotion text similarity.

## Layer 3 — Semantic matching

Optionally use:

```text
pgvector
```

for embedding-based similarity.

---

# 37. Canonical Promotion Selection

When multiple observations represent the same promotion:

```text
Canonical Promotion
        │
        ├── Official retailer evidence
        ├── Marketplace evidence
        ├── News evidence
        └── Aggregator evidence
```

The canonical record should retain multiple evidence records rather than discarding source information.

Prefer the most authoritative source for:

* Promotion validity
* Price
* Dates
* Mechanism
* Product identity

---

# 38. Source Reliability Score

Suggested baseline:

```text
Tier 1 = 1.00
Tier 2 = 0.85
Tier 3 = 0.70
Tier 4 = 0.55
Tier 5 = 0.40
```

These values may be tuned using historical accuracy.

---

# 39. AI Confidence

Every extraction should have:

```text
field-level confidence
overall confidence
```

Example:

```json
{
  "product_confidence": 0.97,
  "price_confidence": 0.99,
  "promotion_type_confidence": 0.98,
  "date_confidence": 0.72,
  "overall_confidence": 0.91
}
```

Low-confidence records should enter the review queue.

---

# 40. Ranking Engine

The Top 10 ranking should consider:

```text
Promotion Strength
Source Reliability
Freshness
Category Relevance
Competitor Importance
AI Confidence
```

Recommended initial formula:

```text
rank_score =
    0.30 * promotion_strength
  + 0.20 * source_reliability
  + 0.15 * freshness
  + 0.15 * category_relevance
  + 0.10 * competitor_importance
  + 0.10 * ai_confidence
```

All component scores must be normalized between:

```text
0.0
```

and

```text
1.0
```

---

# 41. Promotion Strength

Initial suggested values:

| Promotion    | Score |
| ------------ | ----: |
| B1G1         |  1.00 |
| 50% discount |  0.95 |
| B2G1         |  0.90 |
| 40% discount |  0.85 |
| B3G1         |  0.70 |
| 30% discount |  0.75 |
| 20% discount |  0.60 |
| Multibuy     |  0.55 |
| Member price |  0.50 |
| Bundle       |  0.45 |
| Cashback     |  0.40 |
| Gift         |  0.40 |
| Voucher      |  0.40 |
| Other        |  0.20 |

These values are configuration, not hard-coded business truth.

They should eventually be calibrated using actual commercial relevance.

---

# 42. Freshness Score

Freshness should decay over time.

Example:

```text
0 days old       → 1.00
1–7 days         → 0.95
8–30 days        → 0.85
31–60 days       → 0.70
61–90 days       → 0.50
>90 days         → 0.00
```

The exact curve should be configurable.

---

# 43. Category Relevance

The initial target categories are:

```text
BISCUIT
CRACKER
COOKIE
WAFER
SNACK
```

Category relevance should be highest for the core target categories.

Irrelevant products should not enter the Top 10 simply because they have a strong discount.

---

# 44. Top 10 API

Primary endpoint:

```http
GET /api/v1/promotions/top10
```

Example response:

```json
{
  "generated_at": "2026-09-02T10:00:00Z",
  "count": 10,
  "items": [
    {
      "rank": 1,
      "competitor": "Example Competitor",
      "retailer": "Example Retailer",
      "brand": "Example Brand",
      "product": "Example Biscuit 200g",
      "promotion_type": "BUY_X_GET_Y",
      "buy_quantity": 1,
      "free_quantity": 1,
      "regular_price": 20000,
      "promo_price": 10000,
      "start_date": "2026-09-01",
      "end_date": "2026-09-07",
      "source_url": "...",
      "rank_score": 0.94,
      "ai_confidence": 0.98,
      "last_verified": "2026-09-02T09:50:00Z"
    }
  ]
}
```

---

# 45. Promotion Detail API

```http
GET /api/v1/promotions/{promotion_id}
```

The detail endpoint should return:

* Canonical promotion
* Product information
* Competitor
* Retailer
* Promotion mechanism
* Dates
* Price
* Evidence
* Source URLs
* AI confidence
* Crawl history
* Observations
* Ranking score

---

# 46. Filtering API

The API should eventually support:

```text
competitor
brand
retailer
category
promotion_type
status
date range
minimum discount
source tier
```

Example:

```http
GET /api/v1/promotions?promotion_type=BUY_X_GET_Y
```

---

# 47. Dashboard

The MVP dashboard should display:

## Top 10

```text
Rank
Competitor
Brand
Product
Promotion
Price
Discount
Validity
Retailer
Source
Confidence
```

## Filters

```text
Competitor
Retailer
Brand
Promotion type
Category
Active/Expired
Date
```

## Promotion Detail

Display the original source evidence.

---

# 48. Alerts

The platform should eventually support alerts for:

* New B1G1
* New B2G1
* Large discount
* Competitor promotion detected
* Promotion ending soon
* Important competitor activity
* Significant price change

Example alert:

```text
Competitor promotion detected

Competitor: Example Competitor
Brand: Example Brand
Product: Example Biscuit 200g

Promotion: Buy 1 Get 1
Retailer: Example Retailer

Valid until: 7 Sep 2026

Confidence: 97%
```

---

# 49. Object Storage

Raw web evidence should preferably be stored outside PostgreSQL.

Recommended structure:

```text
bucket/
  source/
    year/
      month/
        day/
          crawl_id/
            page.html
            page.pdf
            image-01.png
            screenshot.png
```

Database stores:

```text
raw_content_uri
image_uri
screenshot_uri
```

This keeps PostgreSQL focused on structured data.

---

# 50. Security

## Database

The application role must only have access to:

```text
competitor_intel
```

It must not have access to:

```text
dwh_prod
```

## Credentials

Secrets must not be committed to Git.

Use:

```text
.env
```

locally and a proper secret-management mechanism in production.

## API

The API should eventually implement:

* Authentication
* Authorization
* Rate limiting
* Request validation
* Audit logging

---

# 51. Application Docker Architecture

PostgreSQL is external to Docker.

Docker may run:

```text
┌──────────────────────────────┐
│ Docker Compose               │
│                              │
│ FastAPI                      │
│ Worker                       │
│ Scheduler                    │
│ Redis                        │
│ Playwright/Crawler           │
└──────────────┬───────────────┘
               │
               │ PostgreSQL connection
               ▼
     Existing PostgreSQL Server
               │
               └── competitor_intel
```

There must be no:

```text
postgres:
```

service in the project's Docker Compose file unless explicitly needed for isolated automated tests.

---

# 52. Local Development

Developers should be able to run:

```bash
docker compose up
```

while PostgreSQL remains on the existing server.

Environment:

```env
DATABASE_URL=postgresql+psycopg://competitor_intel_app:<PASSWORD>@<HOST>:5432/competitor_intel
```

If the PostgreSQL server is not reachable from containers, configure the appropriate network route or host address.

Do not solve this by connecting the application to `dwh_prod`.

---

# 53. Testing

Tests must use a separate test database.

Recommended:

```text
competitor_intel_test
```

The test environment must never run against:

```text
dwh_prod
```

Automated tests should include:

### Database

* Migration from empty database
* Rollback
* Constraints
* Indexes
* Foreign keys

### Extraction

* Discount extraction
* B1G1 extraction
* B2G1 extraction
* Bundle extraction
* Member price extraction
* Cashback extraction
* Voucher extraction

### Dates

* Active promotion
* Expired promotion
* Upcoming promotion
* Missing end date
* Three-month cutoff

### Deduplication

* Exact duplicate
* Same promotion from different sources
* Slightly different product naming
* Different observation timestamps

### Ranking

* Strong promotion
* Fresh promotion
* Reliable source
* High-confidence extraction

---

# 54. Acceptance Tests

The MVP is successful when the following conditions are met.

## Database

A completely empty `competitor_intel` database can be initialized using:

```bash
alembic upgrade head
```

No existing database tables are required.

## Isolation

The application can operate without any access to:

```text
dwh_prod
```

## Crawling

The system can crawl at least:

* One retailer website
* One marketplace
* One promotion/news source

## Extraction

The system can correctly extract:

* Product
* Brand
* Price
* Promotion type
* Promotion mechanic
* Dates
* Source
* Evidence
* Confidence

## Ranking

The system returns:

```text
Top 10
```

active promotions.

## Recency

Promotions older than three months are excluded.

## Validity

Expired promotions are excluded from the default Top 10.

## Evidence

Every Top 10 item has a source and evidence.

## Deduplication

The same commercial promotion is not displayed multiple times simply because it appears on several sources.

---

# 55. Recommended Project Structure

```text
competitor-intel/
│
├── app/
│   ├── api/
│   ├── core/
│   ├── db/
│   ├── models/
│   ├── schemas/
│   ├── repositories/
│   ├── services/
│   │   ├── crawler/
│   │   ├── extraction/
│   │   ├── ocr/
│   │   ├── ai/
│   │   ├── validation/
│   │   ├── entity_resolution/
│   │   ├── deduplication/
│   │   └── ranking/
│   ├── workers/
│   └── main.py
│
├── migrations/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
│
├── scripts/
│   ├── create_database.sql
│   ├── seed_sources.py
│   └── seed_reference_data.py
│
├── docker/
│
├── docker-compose.yml
├── Dockerfile
├── alembic.ini
├── pyproject.toml
├── .env.example
├── README.md
└── TECHNICAL_DESIGN.md
```

---

# 56. Database Provisioning Script

The project should provide a script for an administrator to create the database.

Example:

```sql
CREATE ROLE competitor_intel_owner
WITH LOGIN PASSWORD '<OWNER_PASSWORD>';

CREATE DATABASE competitor_intel
OWNER competitor_intel_owner;
```

Then connect to the new database and create the application role:

```sql
CREATE ROLE competitor_intel_app
WITH LOGIN PASSWORD '<APP_PASSWORD>';

GRANT CONNECT ON DATABASE competitor_intel
TO competitor_intel_app;
```

The exact production provisioning process should be documented separately from application migrations because creating a PostgreSQL database requires server-level privileges.

---

# 57. Schema Permissions

After migrations, the application role should receive only the permissions it requires.

Example:

```sql
GRANT USAGE ON SCHEMA competitor_intel
TO competitor_intel_app;

GRANT SELECT, INSERT, UPDATE, DELETE
ON ALL TABLES IN SCHEMA competitor_intel
TO competitor_intel_app;

GRANT USAGE, SELECT, UPDATE
ON ALL SEQUENCES IN SCHEMA competitor_intel
TO competitor_intel_app;
```

Default privileges should also be configured for future tables.

The application role should not be a PostgreSQL superuser.

It should not own the database.

It should not have broad server privileges.

---

# 58. Data Lifecycle

The lifecycle of a promotion is:

```text
DISCOVERED
    ↓
CRAWLED
    ↓
EXTRACTED
    ↓
VALIDATED
    ↓
ENTITY RESOLVED
    ↓
DEDUPLICATED
    ↓
RANKED
    ↓
ACTIVE
    ↓
EXPIRED
```

If extraction fails:

```text
CRAWLED
    ↓
EXTRACTION_FAILED
    ↓
RETRY / REVIEW
```

If confidence is insufficient:

```text
EXTRACTED
    ↓
REVIEW_REQUIRED
```

---

# 59. Observability

The system must log:

* Crawl start
* Crawl completion
* Crawl failures
* Extraction duration
* AI calls
* AI token/cost metrics where available
* Validation failures
* Deduplication decisions
* Ranking execution
* API latency
* Database errors

Metrics should include:

```text
pages_crawled
pages_failed
promotions_extracted
promotions_validated
promotions_rejected
promotions_reviewed
promotions_active
promotions_expired
ai_extraction_success_rate
crawl_success_rate
top10_generation_time
```

---

# 60. AI Cost Control

AI should not be called unnecessarily.

Use a pipeline such as:

```text
URL
 ↓
Fetch
 ↓
Content hash
 ↓
Has content changed?
 ├── NO → skip AI
 └── YES
       ↓
   lightweight extraction
       ↓
   Is promotion likely?
       ├── NO → skip
       └── YES
             ↓
          AI extraction
```

Images and vision models should only be used when required.

---

# 61. Source Priority

The crawler should prioritize sources based on:

```text
business importance
source reliability
historical promotion frequency
freshness
crawl cost
expected information value
```

Example:

```text
Official retailer promotion page
        ↓
Official retailer catalog
        ↓
Official marketplace store
        ↓
Official brand source
        ↓
Promotion aggregator
        ↓
News
        ↓
Social
```

---

# 62. Compliance

The crawler must respect applicable:

* robots.txt
* Terms of Service
* Rate limits
* Copyright restrictions
* Authentication requirements
* Anti-bot restrictions

The system should prioritize publicly available information.

It must not attempt to bypass:

* CAPTCHA
* Login controls
* Access restrictions
* Technical security mechanisms

---

# 63. Future DWH Integration

Integration with `dwh_prod` is explicitly deferred.

The future architecture may be:

```text
competitor_intel
       │
       │ validated export
       ▼
ETL / ELT
       │
       ▼
dwh_prod
```

Possible integration methods:

```text
Scheduled ETL
API
CSV export
Parquet export
Database replication
Data pipeline
```

This should be implemented only after the Competitor Intelligence platform has stable and validated data.

The application itself should continue to remain isolated from `dwh_prod`.

---

# 64. MVP Implementation Order

## Phase 1 — Infrastructure

1. Create `competitor_intel` database.
2. Create dedicated database owner.
3. Create restricted application role.
4. Verify application cannot access `dwh_prod`.
5. Configure environment variables.
6. Configure Alembic.
7. Create initial migration.

## Phase 2 — Database

Implement:

```text
source_registry
crawl_jobs
crawl_documents
promotion_observations
promotions
promotion_evidence
competitors
brands
products
retailers
entity_mapping
review_queue
```

## Phase 3 — Crawler

Implement:

* HTTP crawler
* Playwright crawler
* PDF extraction
* OCR
* Content hashing
* Crawl scheduling

## Phase 4 — AI Extraction

Implement:

* Structured extraction schema
* Evidence extraction
* Confidence scoring
* Date normalization
* Promotion normalization

## Phase 5 — Validation

Implement:

* Required-field validation
* Price validation
* Date validation
* Promotion mechanism validation
* Category validation

## Phase 6 — Entity Resolution

Implement:

* Brand matching
* Product matching
* Retailer matching
* Competitor matching

## Phase 7 — Deduplication

Implement:

* Deterministic matching
* `pg_trgm`
* Optional vector similarity

## Phase 8 — Ranking

Implement:

* Promotion strength
* Freshness
* Source reliability
* Category relevance
* Competitor importance
* AI confidence

## Phase 9 — API

Implement:

```text
GET /api/v1/promotions/top10
GET /api/v1/promotions/{id}
GET /api/v1/promotions
```

## Phase 10 — Dashboard

Implement:

* Top 10
* Filters
* Detail page
* Evidence
* Source links
* Confidence

---

# 65. Definition of Done

The MVP is considered complete when:

* A dedicated `competitor_intel` database exists on the existing PostgreSQL server.
* PostgreSQL itself does not run inside Docker.
* The application has no credentials for `dwh_prod`.
* The database can be initialized from zero using migrations.
* At least three source types can be crawled.
* Promotions can be extracted using AI.
* Evidence is preserved.
* Promotion types are normalized.
* Products and brands can be resolved.
* Duplicate promotions are consolidated.
* Expired promotions are excluded.
* Promotions older than three months are excluded from the default Top 10.
* The system produces a ranked Top 10.
* Each Top 10 promotion has source evidence.
* Low-confidence results can be reviewed.
* Crawl and extraction failures are observable.
* The system can run without modifying any existing DWH infrastructure.

---

# 66. Key Architectural Principle

The most important implementation principle is:

> **Reuse the existing PostgreSQL server, but isolate this application in its own database.**

The architecture therefore deliberately separates:

```text
Infrastructure reuse
        +
Database isolation
        +
Application isolation
        +
Independent schema
```

This provides the lowest implementation risk while avoiding unnecessary duplication of PostgreSQL infrastructure.

`dwh_prod` remains untouched and is not a dependency of the Competitor Promotion Intelligence Platform.
