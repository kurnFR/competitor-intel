# Competitor Intel Search

A flexible competitor intelligence platform for searching companies, products, locations, promotions, and related business activity.

## Product direction

This project was originally scoped around FMCG promotion tracking, but the product is being expanded into a broader discovery and search platform. The system should help users find:

- companies and brands
- products and SKUs
- categories and subcategories
- outlet and channel activity
- promotion campaigns and discount mechanics
- business activity by date and geography
- recent market and competitor signals

## Search goals

The site should support queries like:

- company name search
- product search
- category search
- outlet search
- city or country search
- promotion type search
- active vs expired campaign search
- business activity and launch search

## Core use cases

- Find which companies are active in a city or region
- Search for a product and view related promotion history
- Monitor competitor promotions by outlet or channel
- Compare brands across categories and locations
- Explore company activity beyond promotions, including launches and price changes

## MVP architecture

- FastAPI backend
- PostgreSQL data layer
- SQLAlchemy models
- search endpoints for company/product/promotion discovery
- future web UI and analytics dashboard

## Current implementation status

The project has a working FastAPI application skeleton with:

- app config
- SQLAlchemy database setup
- core model definitions
- company/product/promotion CRUD endpoints
- search endpoint for keyword-based discovery

## Audit-grade product and promotion requirements

For the competitor monitoring workflow, each promotion entry should capture:

- exact product name and variant, such as Roma Kelapa 300gr
- product gram size and carton volume when available
- units per carton or total pieces per pack/carton
- promotion validity start and end date
- geographic scope (city, region, or national)
- source URL, source type, and source timestamp for audit trail
- evidence text summarizing the recorded promotion facts
- verified outlet channel group

This metadata is necessary to answer the business question: which active promotions are currently running, where, for which exact product, and with what verified evidence.

The default active list is ranked by confidence score, source timestamp, discount percentage, and record timestamp. A record is shown as `Verified source` only when it has a non-demo source URL, evidence text, and source timestamp. Seed/demo records are explicitly marked `Unverified source` and must not be treated as confirmed market intelligence.

## Website access and controls

The dashboard requires a sign-in. The development credentials are configured in `.env`:

Open the dashboard at `http://localhost:8002`.

- username and password: use the values configured in `.env`

Change `AUTH_USERNAME`, `AUTH_PASSWORD`, and `AUTH_SECRET` before sharing the service beyond a local development environment. Sessions are stored in an HTTP-only signed cookie and expire after eight hours. The daily schedule is persisted in `schedule.json` and uses UTC time.

The dashboard provides:

- keyword search across company, product, variant, promotion, and evidence
- company, outlet, location, category, channel, active-status, and minimum-discount filters
- top 10 results by default
- a browser-persisted light/dark theme toggle
- sign-out control
- daily automatic scan scheduling in UTC
- horizontally scrollable promotion results on narrow browser windows
- non-clickable `Unverified source` labels when audit links are unavailable

Industry is required and defaults to FMCG when the dashboard opens. When Industry is selected and the other search fields are empty, the dashboard searches all matching records already stored in the database. The scan action then refreshes the same result table, with a maximum of 10 rows shown by default.

Promotion and catalog write endpoints require authentication. Promotion ingestion validates date order, source URL format, evidence, and confidence. Records without complete evidence remain unverified; the API and PostgreSQL constraint prevent unsupported outlet channel values from being stored.

### Verified channel taxonomy

Outlets use one of these controlled channel groups only when verified by source evidence: `Retail`, `Modern Trade`, `General Trade`, `E-commerce`, `Wholesale`, `Distributor`, or `Foodservice`. Unknown or unsupported outlet-channel data is stored as `N/A`, not guessed. Existing generic outlet names such as Indomaret and Alfamart are therefore `N/A` until a source verifies their channel classification.

## Next phase

- add a full Postgres schema and indexes
- add retailer and location tables
- add search relevance ranking
- add filters for category, geography, and activity type
- add web UI and dashboard
- add admin data ingestion and validation routines

## Suggested database direction

The project should use a dedicated PostgreSQL database named competitor_intel, with models for:

- companies
- brands
- products
- retailers
- locations
- promotions
- company activity

This keeps the data model flexible enough to support FMCG and more general competitor search use cases.
