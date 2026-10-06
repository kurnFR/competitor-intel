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

## Login, roles and first-time setup

Everything (dashboard and API) requires a login. There are no default accounts.

1. Run the migrations: `alembic upgrade head` (creates the `users`, `user_sessions` and `audit_log` tables).
2. Create the first administrator (the password is typed at a hidden prompt):
   `python -m scripts.create_user --username yourname --role ADMIN`
3. Sign in at `/login`. Administrators add other users at **Admin** and choose a role:

| Role | Can do |
|------|--------|
| **Viewer** | See the dashboard, Insights (weekly digest, trends), promotion details |
| **Analyst** | Viewer + export CSV/Excel + confirm uncertain matches on **Review** |
| **Admin** | Analyst + start scans, manage users, read the security log |

How it is protected:
* Passwords are hashed with Argon2id; minimum 12 characters, common passwords rejected. New and reset accounts must change the temporary password at first sign-in.
* Sessions are server-side; the browser cookie is `HttpOnly`, `SameSite=Strict` and (in production) `Secure`. Only a hash of the token is stored. Sessions expire after 12 hours, or 2 hours idle, and changing a password signs the user out everywhere else.
* **Two-factor sign-in (optional, recommended):** any user can add a 6-digit authenticator-app code on their **Account** page (QR code + 10 one-time recovery codes). Set `SECRET_KEY` to enable it (it encrypts the stored authenticator secrets - keep it safe and never change it). Set `MFA_REQUIRED_FOR_ADMINS=true` to make it mandatory for administrators. A code cannot be used twice, wrong codes count toward the lockout, and an administrator can reset a user who lost their phone and recovery codes.
* Every state-changing request needs a CSRF token, and every role is checked on the server.
* 5 wrong passwords lock the account for 15 minutes, and too many failures from one IP are throttled. Failed logins give one generic message so usernames cannot be guessed.
* Logins, failures, lockouts, password and user changes are recorded in the security log (Admin page).
* **Run it behind HTTPS** and set `APP_ENV=production` (turns on the `Secure` cookie, HSTS and hides `/docs`). Only set `TRUST_PROXY=true` behind your own reverse proxy.
* The page sends security headers. A full Content-Security-Policy is delivered in *report-only* mode because the UI loads Tailwind and Font Awesome from CDNs; check the browser console, then tighten it (or self-host those files).

## Marketing features

* **Insights** (`/insights`): weekly digest of new promotions, price/mechanic changes and promotions ending within 7 days, plus a per-competitor activity heat-map.
* **Export** (analyst+): CSV or Excel of the current filtered view. Cells that could run as spreadsheet formulas are neutralised.
* **Review** (analyst+): approve or reject uncertain product/brand/retailer matches (approval links the promotion to the suggested entity), and decide **conflicts**: when two comparable sources report different values for the same promotion, the stored values are frozen, the promotion is hidden from the Top 10, and you choose *use new values* or *keep current*. Both observations are always kept.
* **Weekly e-mail digest** (optional): set `SMTP_HOST`, `SMTP_FROM`, `DIGEST_RECIPIENTS`; sent on `DIGEST_DAY_OF_WEEK` at `DIGEST_HOUR`. Test now with `python -m scripts.send_digest`.
* **JavaScript-only retailer pages** need a browser: `pip install -r requirements-browser.txt && playwright install chromium`. Without it the crawler logs a warning and those pages yield nothing.

* **Price comparison** (`/compare`, analyst+): enter your own products (or import a CSV), and see how competitor promotions compare per 100 g, with the biggest undercuts first. Buy-X-get-Y offers are converted to an effective price; only promotions with a computable price and a similar pack size are compared.
* **Regional pricing** (`/regional`): the same product's price per region side by side. Where a promotion's page does not state a region it is shown as *Not stated*, never as nationwide.
* **Websites we scan** (Admin page): a new website is a *candidate* and is never scanned until an administrator approves it and confirms the reader (adapter); each source has its own schedule and health (OK / failing / stale). A failed scan is never treated as "no promotions". Recent scans are listed there too. Addresses pointing at private or internal networks are refused, and the crawler refuses to follow redirects into them.
* **Chat digest** (optional): set `DIGEST_WEBHOOK_URL` (Slack, Google Chat, Mattermost) to post the weekly digest to a channel.

## Measuring extraction quality

The LLM decides what counts as a promotion, so measure it on your real sources:

```bash
python -m scripts.try_extract page.txt          # see accepted / rejected items for one page
python -m scripts.eval_extraction --min-f1 0.8  # score against labelled pages in tests/fixtures/extraction_gold/
```

Label 15-30 real pages (`name.txt` + `name.json`, see the sample). Re-run after changing the model or prompt.

## Is my installation set up correctly?

`python -m scripts.preflight [--llm]` (or **Admin -> Setup checklist**) checks the database and migrations, security settings, administrator accounts, the LLM, websites, recent scans and the review backlog, and tells you what to fix. It never shows secret values. Start with `docs/FIRST_RUN.md`.

## Testing a page without scanning (and "why is this hidden?")

`python -m scripts.dry_run page.html [--retailer NAME]` runs one real page through the same extraction, matching and storage
code as a scan inside a transaction that is always rolled back, and reports for every promotion whether it would appear on the
dashboard and, if not, which rule hides it and how to fix it. The Setup checklist shows the same reasons, with counts, for what
is already stored.

## More documentation

* `docs/FIRST_RUN.md` - step-by-step checklist for the first real run
* `docs/PRD_ALIGNMENT.md` - requirement-by-requirement status and open decisions
* `docs/DEPLOYMENT.md` - Docker Compose / server setup, HTTPS, backups, upgrade, troubleshooting
* `docs/HANDOVER.md` - what is built, what you still need to do, and how to operate it
* `tests/ui/README.md` - the click-through UI test

## Automatic tests on GitHub

`.github/workflows/ci.yml` runs the full test suite against PostgreSQL on every push and pull request.

## Security & Operations

* **Automation key.** `ADMIN_API_KEY` is optional; it lets a cron job or CI call `POST /api/v1/pipeline/run` (header `X-API-Key`) without a login. If empty, only signed-in administrators can start scans.
* **CORS.** Same-origin only by default; list extra origins in `CORS_ORIGINS` (comma-separated).
* **Crawler etiquette.** The crawler identifies itself with `CRAWLER_USER_AGENT` (add a contact URL/e-mail) and
  honours each site's `robots.txt` (`CRAWLER_RESPECT_ROBOTS=true`). Review each retailer's terms of use before
  enabling a source.
* **One scan at a time.** A PostgreSQL advisory lock stops the scheduler, manual scans and extra workers from
  overlapping. Scan status is tracked per process, so run a single uvicorn worker (`scripts/start_server.sh`).
* **Unchanged pages** are not re-sent to the LLM; their promotions are simply marked as still seen. Use
  `run_pipeline(force=True)` to re-extract.
* **Undated promotions.** Catalog pages often omit validity dates. Such promotions are still shown (flagged
  "Dates not stated", ranked slightly lower) for `UNDATED_PROMO_MAX_AGE_DAYS` after they were last seen.
* **Rankings** are recalculated every `EXPIRATION_CHECK_MINUTES`, so freshness decays even without a re-crawl.

## Automated Background Jobs
* **Crawl & Extraction Pipeline**: Runs automatically every 30 minutes via APScheduler.
* **Expiration Worker**: Runs every 15 minutes to transition promotions past their end date from `ACTIVE` to `EXPIRED`, and stale records (>7 days without end date) to `UNKNOWN`.

To run the crawler once per day, set `CRAWL_INTERVAL_MINUTES=1440` in `.env` and restart the server. The scheduler uses UTC and requires the application process to remain running. `Scan now` starts an immediate one-off scan and does not change the daily schedule.

---

## Testing
```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_api.py -v
```
