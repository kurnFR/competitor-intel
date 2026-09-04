# DATA_MODEL.md — Canonical PostgreSQL Data Model

## 1. Purpose

This document defines the logical data model for `competitor_intel`.

The model separates source discovery, raw source observations and canonical commercial entities. This is required for multi-source monitoring, auditability, historical changes, regional pricing and safe deduplication.

## 2. Data Layers

```text
SOURCE CONTROL
  source_registry
  source_urls
  crawl_jobs
  crawl_documents

AI OBSERVATION
  extraction_runs
  promotion_observations

MASTER DATA
  competitors
  brands
  products
  retailers
  geography_reference

CANONICAL PROMOTION
  promotions
  promotion_geographies
  promotion_conditions

PROVENANCE
  promotion_evidence

QUALITY
  validation_results
  entity_mapping
  review_queue
```

## 3. Core Relationships

```text
source_registry
   1 ─── N source_urls
   1 ─── N crawl_jobs
source_urls
   1 ─── N crawl_jobs
crawl_jobs
   1 ─── N crawl_documents
crawl_documents
   1 ─── N extraction_runs
crawl_documents
   1 ─── N promotion_observations

competitors
   1 ─── N brands
brands
   1 ─── N products

promotions
   N ─── 1 competitor
promotions
   N ─── 1 brand
promotions
   N ─── 1 product
promotions
   N ─── 1 retailer
promotions
   1 ─── N promotion_geographies
promotions
   1 ─── N promotion_conditions
promotions
   1 ─── N promotion_evidence
```

## 4. Source Registry

A source is a domain/site family; a source URL is an individual crawl target.

### source_registry

```text
id UUID PK
name TEXT NOT NULL
base_url TEXT NOT NULL
domain TEXT NOT NULL
source_type TEXT NOT NULL
owner_name TEXT NULL
tier INTEGER
reliability_score NUMERIC(5,4)
priority INTEGER
crawl_frequency_minutes INTEGER
adapter_key TEXT
access_status TEXT
is_active BOOLEAN
last_discovery_at TIMESTAMPTZ
last_crawled_at TIMESTAMPTZ
last_success_at TIMESTAMPTZ
last_error_at TIMESTAMPTZ
created_at TIMESTAMPTZ
updated_at TIMESTAMPTZ
```

### source_urls

```text
id UUID PK
source_id UUID FK
url TEXT NOT NULL
canonical_url TEXT NULL
page_type TEXT
category_hint TEXT
crawl_priority INTEGER
crawl_frequency_minutes INTEGER NULL
is_active BOOLEAN
last_crawled_at TIMESTAMPTZ
last_success_at TIMESTAMPTZ
last_http_status INTEGER
last_content_hash TEXT
failure_count INTEGER
next_crawl_at TIMESTAMPTZ
created_at TIMESTAMPTZ
updated_at TIMESTAMPTZ
```

This table is important: the next scheduled run should primarily use approved URLs already known to the system. New URLs can enter through periodic discovery.

## 5. Data Source Examples

The registry must be able to represent:

- official company/brand websites
- official retailer and modern-trade websites
- local/regional retail websites
- verified marketplace stores
- public e-commerce pages where permitted
- promotion aggregators
- established news/media
- public social/content sources where permitted

Hemat.id is an initial source, not the only source.

## 6. Crawl Jobs

```text
id UUID PK
source_id UUID FK
source_url_id UUID NULL FK
url TEXT
job_type TEXT
status TEXT
started_at TIMESTAMPTZ
completed_at TIMESTAMPTZ
http_status INTEGER
error_code TEXT
error_message TEXT
retry_count INTEGER
content_hash TEXT
created_at TIMESTAMPTZ
```

Statuses:

```text
QUEUED
RUNNING
SUCCESS
FAILED
BLOCKED
SKIPPED
```

A successful crawl with zero promotions is still `SUCCESS`.

## 7. Crawl Documents

```text
id UUID PK
crawl_job_id UUID FK
source_id UUID FK
url TEXT NOT NULL
canonical_url TEXT
content_type TEXT
title TEXT
raw_content_uri TEXT
text_content TEXT
content_hash TEXT
published_at TIMESTAMPTZ
retrieved_at TIMESTAMPTZ
language_code TEXT
http_status INTEGER
metadata JSONB
created_at TIMESTAMPTZ
```

Use SHA-256 for content hashing.

## 8. Extraction Runs

```text
id UUID PK
document_id UUID FK
model_name TEXT
prompt_version TEXT
schema_version TEXT
started_at TIMESTAMPTZ
completed_at TIMESTAMPTZ
status TEXT
raw_response JSONB
error_message TEXT
created_at TIMESTAMPTZ
```

## 9. Promotion Observations

This is the immutable observation layer.

```text
id UUID PK
document_id UUID FK
extraction_run_id UUID FK
source_promotion_key TEXT
raw_extracted JSONB
normalized_extracted JSONB
observed_at TIMESTAMPTZ
created_at TIMESTAMPTZ
```

An observation answers:

> What did source X show at time T?

Never overwrite historical observations merely because the same promotion is seen again.

## 10. Master Data

Competitors, brands, products and retailers are canonical reference entities. Unknown entities remain unresolved until sufficient evidence exists.

Unknown manufacturer/competitor must not be replaced with placeholders such as `FMCG Manufacturer`.

## 11. Geography Model

Do not use `promotions.geography` as the sole canonical representation.

### geography_reference

```text
id UUID PK
parent_id UUID NULL FK
scope_type TEXT
name TEXT
normalized_name TEXT
country_code TEXT
is_active BOOLEAN
mapping_version TEXT
created_at TIMESTAMPTZ
updated_at TIMESTAMPTZ
```

Scope types:

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

### promotion_geographies

```text
id UUID PK
promotion_id UUID FK
geography_id UUID NULL FK
scope_type TEXT NOT NULL
scope_name TEXT NOT NULL
source_text TEXT NOT NULL
scope_role TEXT NOT NULL
confidence NUMERIC(5,4)
created_at TIMESTAMPTZ
```

`scope_role` is `INCLUDE` or `EXCLUDE`.

Example:

```text
INCLUDE | REGION      | Jawa
INCLUDE | REGION      | Bali
INCLUDE | REGION      | Lombok
EXCLUDE | STORE_GROUP | Indomaret Point
```

Never silently expand a commercial area into administrative areas.

## 12. Canonical Promotions

Use `NUMERIC(18,2)` for money.

Material identity dimensions are:

```text
product
retailer
channel
promotion mechanic
mechanic parameters
price
validity
geographic scope
conditions
```

Regional or channel differences that materially affect commercial applicability must not be merged.

## 13. Promotion Conditions

```text
id
promotion_id
condition_type
condition_value_text
condition_value_numeric
source_text
created_at
```

Examples: `MEMBER_ONLY`, `MINIMUM_PURCHASE`, `MAXIMUM_QUANTITY`, `PAYMENT_METHOD`, `APP_ONLY`, `STORE_EXCLUSION`, `GEOGRAPHY_EXCLUSION`, `VOUCHER_CODE`.

## 14. Evidence

Every verified canonical promotion must have evidence.

```text
promotion_evidence
------------------
id UUID PK
promotion_id UUID FK
document_id UUID FK
field_name TEXT
evidence_text TEXT
source_url TEXT
page_number INTEGER NULL
locator JSONB NULL
confidence NUMERIC(5,4)
created_at TIMESTAMPTZ
```

Evidence should support price, mechanic, validity and geography separately where practical.

## 15. Validation and Review

Validation results should record rule, result, severity and timestamp. Review queue records unresolved material issues.

## 16. Status

```text
UPCOMING
ACTIVE
EXPIRED
UNKNOWN
REVIEW_REQUIRED
REJECTED
```

## 17. Freshness

Default Top 10 freshness:

```sql
last_verified_at >= NOW() - INTERVAL '90 days'
```

For open-ended promotions, use a stricter configured verification window, recommended 7 days for MVP.

## 18. Deduplication

Candidate matching must consider product, retailer, channel, promotion type, mechanic parameters, price, validity, geography inclusions/exclusions and material conditions.

Two sources can support the same canonical promotion. Two regional observations can remain separate canonical promotions when commercially material.

## 19. Recommended Indexes

```sql
CREATE INDEX idx_promotions_status_end
ON competitor_intel.promotions(status, end_date);

CREATE INDEX idx_promotions_last_verified
ON competitor_intel.promotions(last_verified_at DESC);

CREATE INDEX idx_promotions_category
ON competitor_intel.promotions(category);

CREATE INDEX idx_promotions_retailer
ON competitor_intel.promotions(retailer_id);

CREATE INDEX idx_promotions_product
ON competitor_intel.promotions(product_id);

CREATE INDEX idx_promotions_brand
ON competitor_intel.promotions(brand_id);

CREATE INDEX idx_source_urls_due
ON competitor_intel.source_urls(is_active, next_crawl_at);

CREATE INDEX idx_source_urls_hash
ON competitor_intel.source_urls(last_content_hash);

CREATE INDEX idx_geo_scope_name_trgm
ON competitor_intel.promotion_geographies
USING gin (scope_name gin_trgm_ops);
```

Add indexes based on actual query plans.

## 20. Constraints

Recommended database invariants:

```text
money >= 0
confidence between 0 and 1
reliability between 0 and 1
end_date >= start_date when both are known
buy_quantity > 0 when supplied
free_quantity >= 0 when supplied
```

## 21. Historical Integrity

Never delete raw observations because a promotion expired or a source was disabled. Source registry status and canonical promotion status are independent.

## 22. Analytics

Prefer views/API queries for active counts, expiring promotions, competitor activity, geography distribution, regional price comparison, source freshness and Top 10 ranking until query volume requires materialized aggregates.
