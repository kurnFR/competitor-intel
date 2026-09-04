# DATA_MODEL.md — Canonical PostgreSQL Data Model

## 1. Purpose

This document defines the logical data model for `competitor_intel`.

The model separates raw source observations from canonical commercial entities. This is required for auditability, historical changes, regional pricing and safe deduplication.

## 2. Data Layers

```text
SOURCE
  source_registry
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
   1 ─── N crawl_jobs
   1 ─── N crawl_documents

crawl_documents
   1 ─── N extraction_runs
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

## 4. Important Modeling Rule

Do not use `promotions.geography` as the sole canonical geography representation.

A promotion may apply to multiple areas and may have exclusions.

Use:

```text
promotions.source_geography_text
promotion_geographies.scope_role
promotion_geographies.scope_type
promotion_geographies.scope_name
promotion_geographies.source_text
```

## 5. Geography Examples

### Simple region

```text
source_geography_text:
Berlaku di Jawa

promotion_geographies:
INCLUDE | REGION | Jawa
```

### Multiple regions

```text
INCLUDE | REGION | Jawa
INCLUDE | REGION | Bali
INCLUDE | REGION | Lombok
```

### Inclusion + retailer/store exclusion

```text
INCLUDE | REGION | Jawa
INCLUDE | REGION | Bali
INCLUDE | REGION | Lombok
EXCLUDE | STORE_GROUP | Indomaret Point
```

### Metro/city scope

```text
INCLUDE | METRO | Jabodetabek
INCLUDE | CITY | Palembang
```

Do not expand these scopes automatically unless a versioned mapping is explicitly configured.

## 6. Money

All IDR monetary fields must use:

```sql
NUMERIC(18,2)
```

Never use `FLOAT` for money.

## 7. Promotion Identity

A canonical promotion represents a commercially coherent activity, not simply a product.

Material dimensions include:

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

If two observations differ materially by region, price or condition, they must not be merged merely because product and retailer match.

## 8. Observation vs Canonical Promotion

### Observation

Immutable statement:

> What did source X show at time T?

### Canonical promotion

Current normalized commercial representation:

> What promotion does the system currently believe is active?

Multiple observations may support one canonical promotion.

One source may also produce different observations over time as a promotion changes.

## 9. Evidence

Evidence must be attached at the field or passage level when practical.

Minimum evidence coverage for a verified promotion:

- product identity
- promotion mechanic
- promotional price or benefit
- validity or source recency
- geography when geography is claimed

## 10. Status

Canonical status values:

```text
UPCOMING
ACTIVE
EXPIRED
UNKNOWN
REVIEW_REQUIRED
REJECTED
```

## 11. Recommended Indexes

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

CREATE INDEX idx_geo_scope_name_trgm
ON competitor_intel.promotion_geographies
USING gin (scope_name gin_trgm_ops);
```

Add indexes based on actual query plans rather than indexing every column.

## 12. Constraints

Recommended constraints include:

```text
regular_price >= 0
promo_price >= 0
cashback_amount >= 0
voucher_amount >= 0
confidence between 0 and 1
reliability between 0 and 1
end_date >= start_date when both are known
buy_quantity > 0 when supplied
free_quantity >= 0 when supplied
```

Use database constraints for invariants that should never be violated.

## 13. Referential Integrity

Use foreign keys within `competitor_intel`.

Do not create cross-database foreign keys to `dwh_prod`.

## 14. Historical Integrity

Never delete raw observations merely because a promotion expired.

Canonical promotion status may change from `ACTIVE` to `EXPIRED`, while historical evidence remains available.

## 15. Analytics Views

Prefer database views or API queries for derived metrics such as:

- active promotion count
- promotions expiring in 7 days
- promotion count by competitor
- promotion count by geography
- regional price comparison
- source freshness

Do not persist redundant aggregates until query volume demonstrates the need.
