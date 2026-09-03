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

## Automated Background Jobs
* **Crawl & Extraction Pipeline**: Runs automatically every 30 minutes via APScheduler.
* **Expiration Worker**: Runs every 15 minutes to transition promotions past their end date from `ACTIVE` to `EXPIRED`, and stale records (>7 days without end date) to `UNKNOWN`.

---

## Testing
```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_api.py -v
```
