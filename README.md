# FMCG Competitor Promotion Intelligence Platform

An automated, AI-powered competitor marketing intelligence system for the Indonesian FMCG snack category (biscuits, crackers, cookies, wafers).

The platform continuously monitors retailer websites and promotional feeds, extracts structured commercial promotion data using an LLM gateway (9router), validates dates and prices against business rules, deduplicates multi-source observations, ranks activities by commercial impact, and serves the **Top 10 Active Competitor Promotions** via REST API and a web dashboard.

The dashboard defaults to Industry `FMCG` and uses `Outlet` terminology. Its free-text search and filters query the stored Top 10 promotion data, including product, pack size, promotion mechanic, outlet, channel, geography, validity, and audit evidence. Channel values outside the verified taxonomy are displayed as `N/A` rather than inferred.

---

## Architecture Overview

```
                          PUBLIC SOURCES
             (Retailer Catalogs, Aggregators, Promo Pages)
                               │
                               ▼
                        Source Crawlers
              (httpx + BeautifulSoup + Trafilatura)
                               │
                               ▼
                       Raw Evidence Store
               (Crawl Documents + Content Hash SHA256)
                               │
                               ▼
                     AI Extraction Engine
             (9router: hermes-auto-fallback / JSON Schema)
                               │
                               ▼
                      Validation Engine
              (Date validity, 3-month rule, Price logic)
                               │
                               ▼
                      Entity Resolution
               (pg_trgm fuzzy matching + Canonical DB)
                               │
                               ▼
                        Deduplication
              (Consolidates identical commercial promotions)
                               │
                               ▼
                       Ranking Engine
            (Multi-factor score: Strength, Reliability, Freshness)
                               │
                               ▼
                 PostgreSQL: competitor_intel
                (Isolated database, schema-scoped)
                               │
                  ┌────────────┴────────────┐
                  ▼                         ▼
              REST API                  Dashboard
        (GET /api/v1/promotions/top10)   (Web Interface)
```

---

## Database Schema (PostgreSQL)

Located in database `competitor_intel` under schema `competitor_intel`:

* `source_registry`: Monitored sources with tiers (Tier 1-5), reliability scores, and crawl schedules.
* `crawl_jobs`: Execution tracking and HTTP statuses for each crawl cycle.
* `crawl_documents`: Raw crawled HTML, extracted text, and SHA-256 content hashes.
* `competitors`: Parent FMCG companies (Mayora, Khong Guan, Mondelez, Garudafood, Nabati, etc.).
* `brands`: Competitor brands (Roma, Oreo, Nissin, Beng Beng, Gery, etc.).
* `products`: Canonical products with pack sizes and category mapping.
* `retailers`: Monitored channels (Indomaret, Alfamart, Superindo, Hypermart, Transmart, Yogya).
* `promotion_observations`: Raw AI extraction outputs per document for full auditability.
* `promotions`: Canonical active promotions with prices, discounts, mechanics, validity, and rank scores.
* `promotion_evidence`: Audit trail linking each promotion to exact source text quotes and URLs.
* `entity_mapping`: Fuzzy and exact resolution mapping records.
* `review_queue`: Flagged low-confidence records requiring human review.

---

## Getting Started

### Prerequisites
* **Python 3.12+** (configured via `pyenv` or virtualenv)
* **PostgreSQL 12+** with extensions `pg_trgm` and `uuid-ossp`
* **9router LLM Gateway** on `http://localhost:20128/v1`

### Installation
```bash
# 1. Clone repository
git clone https://github.com/kurnFR/competitor-intel.git
cd competitor-intel

# 2. Set up virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env with your PostgreSQL credentials and LLM settings
```

### Running Database Migrations
```bash
alembic upgrade head
```

### Seeding Reference Data
```bash
PYTHONPATH=. python3 scripts/seed_data.py
```

### Running the Extraction Pipeline Manually
```bash
PYTHONPATH=. python3 scripts/run_pipeline.py
```

`Refresh` only reloads promotions already stored in PostgreSQL. To collect new promotion data, click `Scan now` in the dashboard or run the command above. The scan needs reachable source websites and, for AI extraction, the configured LLM gateway. Records without usable evidence are not treated as verified.

### Starting the Web Server & Dashboard
```bash
./scripts/start_server.sh
# Server starts at http://0.0.0.0:8000
```

---

## API Reference

### 1. Top 10 Active Promotions
`GET /api/v1/promotions/top10`

Query Parameters:
* `category`: Filter by category (e.g. `BISCUIT`, `CRACKER`, `WAFER`, `COOKIE`, `SNACK`)
* `retailer`: Filter by retailer name (e.g. `Indomaret`, `Alfamart`, `Superindo`, `Hypermart`)
* `brand`: Filter by brand name (e.g. `Roma`, `Oreo`, `Nissin`)
* `competitor`: Filter by manufacturer (e.g. `Mayora`, `Mondelez`)
* `days`: Recency cutoff in days (default `90` for the 3-month rule)

Example Request:
```bash
curl "http://localhost:8000/api/v1/promotions/top10?category=WAFER&retailer=Indomaret"
```

### 2. Promotion Audit Detail
`GET /api/v1/promotions/{promotion_id}`

Returns full metadata, rank score components, and all verified source quotes/evidence.

### 3. System Statistics
`GET /api/v1/stats/`

Returns counts of active promotions, competitors tracked, brands monitored, retailers, and promotions expiring within 7 days.

### 4. Health Check
`GET /health`

---
## 45. Web Application & User Interface

The system provides a web-based interface accessible from the left panel with the following navigation:

### 45.1 Left Panel Navigation

**Home**
- Dashboard with KPI cards showing active promotions count, competitors tracked, brands, retailers
- Quick links to Top 10 active promotions
- Summary of recent additions and promotions expiring soon

**Settings** (expandable/collapsible)
- **Master Data** - View and manage all reference tables (competitors, brands, products, retailers, sources)
  - CRUD operations supported with role-based permissions
  - Filterable and searchable data grids
  - Product categories: biscuits, crackers, cookies, wafers, sandwich biscuits, cream biscuits, sweet biscuits, savory crackers, related snack products
- **Source Management** - Configure and add new data sources manually
  - Add new sources with name, domain, type, reliability score, crawl frequency
  - Toggle source active/inactive status
  - Configure crawl frequency per source tier
- **User Permissions** - Manage role-based access control
  - Role definitions: Admin (full CRUD), Editor (add/edit promotions/products), Viewer (read-only), Crawler (source config only)
  - Permission matrix controlling access to master data operations

### 45.2 Master Data Management

Data tables with CRUD support:
- **Competitors** - Manage competitor brands/entities (Admin/Editor can create/edit, Viewer can read)
- **Brands** - Manage product brands under competitors
- **Products** - Manage product catalog (biscuits, crackers, wafers, cookies, etc.) with category validation
- **Retailers** - Manage retailer/channels (Indomaret, Alfamart, Shopee, Tokopedia, Lazada, etc.)
- **Source Registry** - Manage data source configuration for crawlers
- **Promotions** - View and manage promotion records

CRUD Operations by Role:

| Operation | Competitors | Brands | Products | Retailers | Sources | Promotions |
|-----------|-------------|--------|----------|-----------|---------|------------|
| **Create** | Admin, Editor | Admin, Editor | Admin, Editor | Admin, Editor | Admin | Admin, Editor |
| **Read** | All users | All users | All users | All users | All users | All users |
| **Update** | Admin, Editor | Admin, Editor | Admin, Editor | Admin, Editor | Admin | Admin, Editor |
| **Delete** | Admin only | Admin only | Admin only | Admin only | Admin only | Admin only |

### 45.3 Manual Source Addition

Workflow for users discovering new source websites:
1. Navigate to Settings → Source Management → Add New Source
2. Fill in source details: name, domain, source type (retailer, marketplace, aggregator, social, news), reliability score (0.0000-1.0000), country (e.g., Indonesia), crawl frequency (minutes), robots.txt compliance
3. Save source - added to registry and available for crawling
4. Optional: Add initial test URL to verify crawling works

### 45.4 Manual Promotion Entry

1. Navigate to Settings → Master Data → Add Promotion Manually
2. Fill in promotion details: competitor brand, product name/variant, pack size, promotion type (DISCOUNT, BUY_X_GET_Y, MULTIBUY, CASHBACK, VOUCHER, GIFT_WITH_PURCHASE, MEMBER_PRICE, BUNDLE), regular price (IDR), promo price (IDR), discount percentage, buy quantity, free quantity, minimum purchase, start date, end date, retailer, channel, geography, source URL, evidence text, AI confidence
3. Save promotion - record added with status DISCOVERED, lower default AI confidence (e.g., 0.70)
4. Manual entries maintain evidence trail and can be flagged for admin review

### 45.5 User Roles & Permissions

| Role | Competitors | Brands | Products | Retailers | Sources | Promotions | Settings |
|------|-------------|--------|----------|-----------|---------|------------|----------|
| **Admin** | ✓ (CRUD) | ✓ (CRUD) | ✓ (CRUD) | ✓ (CRUD) | ✓ (CRUD) | ✓ (CRUD) | ✓ (Full access) |
| **Editor** | ✓ (CRUD) | ✓ (CRUD) | ✓ (CRUD) | ✓ (CRUD) | ✓ (CRUD) | ✓ (CRUD add/edit) | ✓ (Add/edit only) |
| **Viewer** | ✓ (Read) | ✓ (Read) | ✓ (Read) | ✓ (Read) | ✗ | ✓ (Read) | ✗ |
| **Crawler** | ✗ | ✗ | ✗ | ✗ | ✓ (Config) | ✗ | ✗ |

### 45.6 Search Functionality

- **Global search bar** accessible from left panel
- **Searchable fields**: product name, brand, competitor, retailer, promotion type, discount percentage, date range, category, geography
- **Filter panels** (collapsible): competitor/brand, retailer, promotion type, price range, date range, category
- **Results display**: table view with key promotion fields, pagination, export (CSV, Excel), quick view modal

### 45.7 Integration with Data Collection

- Manual entries follow same validation as automated crawls
- Manually added promotions get lower default AI confidence (0.70 vs typical 0.85-0.98)
- Manual sources can be added to source registry for future automated crawling
- All manual entries maintain evidence trail and audit history
- Manual entries can be promoted to verified status by admin review

---

## Automated Background Jobs
* **Crawl & Extraction Pipeline**: Runs automatically every 30 minutes via APScheduler.
* **Expiration Worker**: Runs every 15 minutes to transition promotions past their end date from `ACTIVE` to `EXPIRED`, and stale records (>7 days without end date) to `UNKNOWN`.

To run the crawler once per day, set `CRAWL_INTERVAL_MINUTES=1440` in `.env` and restart the server. The scheduler uses UTC and requires the application process to remain running. `Scan now` starts an immediate one-off scan and does not change the daily schedule.

---

## Testing
```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_api.py -v
```
