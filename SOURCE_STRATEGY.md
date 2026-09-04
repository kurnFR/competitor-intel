# SOURCE_STRATEGY.md — Multi-Source Discovery, Registry & Collection

## Purpose

Competitor Intel is a multi-source promotion intelligence platform, not a single-source scraper. The system discovers candidate public sources, evaluates them, registers approved sources and useful URLs, then continuously crawls the registered inventory.

Hemat.id is only an initial source adapter, not the permanent source of truth.

## Source categories

The registry may contain:

- Official manufacturer and brand websites
- Official retailer / modern-trade websites
- Regional and local retailer websites
- Public e-commerce and marketplace pages where collection is permitted
- Public campaign, catalog, flyer and promotion pages
- Public news and media pages containing promotion evidence
- Other approved public sources discovered by the system or added by an administrator

Examples include brand sites, Superindo, Alfamart, Indomaret, Hypermart, Tokopedia, Shopee, TikTok Shop and local retailers. These are examples, not a guarantee that every platform can or should be crawled.

## Public-access collection policy

The crawler may use standard HTTP clients, browser automation, JavaScript rendering, public feeds, sitemaps and publicly exposed endpoints to collect information that is accessible without authentication and may be collected under the source's applicable terms and restrictions.

The system must not circumvent authentication, CAPTCHA challenges, paywalls, private data, private APIs, or technical controls specifically intended to restrict automated access.

If a source becomes inaccessible, the crawler records the reason and stops that collection path. It must not repeatedly hammer the source or attempt increasingly aggressive bypasses.

## Source lifecycle

```text
DISCOVERED → CANDIDATE → ASSESSED → APPROVED → ACTIVE
                                      ↓
                         HEALTHY / WARNING / STALE
                                      ↓
                         BLOCKED / DISABLED / MANUAL_ONLY
```

Only APPROVED and ACTIVE sources are eligible for scheduled crawling.

## Source registry

`source_registry` is the control plane for collection.

Minimum concepts:

```text
source_id
canonical_name
domain
source_type
market
authority_level
public_access_status
access_mode
crawl_frequency
priority
status
first_discovered_at
last_assessed_at
last_successful_crawl_at
failure_count
notes
```

Recommended `access_mode` values:

- HTTP
- BROWSER
- PUBLIC_API
- FEED
- SITEMAP
- MANUAL

Recommended access statuses:

- ACTIVE
- JS_REQUIRED
- RATE_LIMITED
- BLOCKED
- LOGIN_REQUIRED
- CAPTCHA_REQUIRED
- PAYWALL
- DISABLED
- MANUAL_ONLY

## URL registry

A source is not enough. The system should register useful URLs or URL patterns within each source.

Each URL record should track:

- source_id
- URL and canonical URL
- page type
- category hint
- crawl priority
- crawl frequency
- active state
- last crawled
- last successful crawl
- last content hash
- HTTP status
- failure count
- next crawl time

This lets future runs focus on known high-value targets instead of repeatedly searching the entire internet.

## Normal scan vs discovery scan

### Normal scan

The normal scheduled run uses approved sources and URLs:

```text
Approved source registry
        ↓
URLs due for crawl
        ↓
Fetch / browser render
        ↓
Content change detection
        ↓
Extract only changed/new content
```

### Discovery scan

A separate periodic process searches for new candidate sources and useful URLs within approved domains. Discovery may use search engines, sitemaps, RSS/feeds, site navigation, category pages, retailer promotion pages and public indexes.

Discovery results first enter the source/URL candidate queue. They do not automatically become trusted canonical promotion data.

## Adaptive crawling

Not every URL needs the same frequency.

```text
High-value promotion page        frequent
Retailer weekly promotion page   frequent
Stable product page              moderate
Company catalog                  moderate
Recent news                      event/recent based
Historical page                  low frequency
Failed/blocked URL               backoff/manual review
```

Prioritize using promotion yield, freshness needs, source priority, recent changes, active promotion periods, crawl success and failure state.

## Content change detection

Where practical, compare content hashes or other stable fingerprints before expensive AI extraction.

```text
crawl → unchanged → skip extraction
crawl → changed   → extract → validate → persist observation
```

Dynamic sources may require source-specific change detection.

## Source-specific adapters

Use an adapter per source family where structure differs:

```text
HematAdapter
RetailerAdapter
BrandWebsiteAdapter
MarketplaceAdapter
NewsAdapter
```

Adapters handle source-specific discovery and extraction. Shared services handle validation, geography normalization, entity resolution, promotion matching and ranking.

## Source reliability

Track:

```text
crawl success rate
blocked rate
content change rate
extraction success rate
evidence coverage
geography resolution rate
historical contradiction rate
review rate
```

Reliability adjustments must be auditable.

## Source authority

Default guidance:

```text
Direct official promotion/retailer evidence
        > verified official store evidence
        > trusted promotion intelligence
        > established media
        > public social/other
```

Authority is context-dependent. Lower-tier observations are not silently deleted when a higher-tier observation exists.

## Multi-source conflict handling

When sources disagree:

1. retain both observations
2. compare timestamps
3. compare source reliability
4. compare geographic scope
5. compare retailer/channel
6. determine whether the records represent different commercial activities
7. send material unresolved conflicts to review

Never overwrite one source simply because another source arrived later.

## Regional and local source strategy

Regional and local sources are first-class sources. Preserve source geography exactly as observed and store normalized geography separately. Never convert a regional promotion into nationwide coverage without evidence.

## Source freshness

Keep these concepts separate:

- `last_successful_crawl_at`: source collection time
- `last_seen_at`: observation time
- `last_verified_at`: validation time
- `valid_from` / `valid_until`: stated commercial validity

A fresh crawl does not automatically mean the promotion is valid today.

## Source onboarding acceptance criteria

A source is production-ready when:

1. Domain and source type are registered.
2. Public access mode is understood.
3. Relevant promotion/product URLs are registered.
4. Parser/browser strategy is documented.
5. Evidence can be retained.
6. Geography can be extracted or explicitly marked unknown.
7. Price and promotion conditions can be extracted or explicitly marked unknown.
8. Failure and stale states are observable.
9. Fixture/test data exists.
10. The source can be disabled without code changes.

## Initial rollout

Do not crawl every possible website on day one.

### Wave 1

- Hemat.id
- selected official retailer promotion pages
- selected official brand/manufacturer pages

### Wave 2

- additional modern trade
- convenience retail
- verified marketplace stores

### Wave 3

- e-commerce/search-rich sources
- established news/media
- regional/local retailers

### Wave 4

- additional public social/content sources where compliant

Adding a source should be a configuration + adapter task, not a rewrite of the canonical promotion model.

## What the next run should do

A normal scheduled run should:

1. load active approved sources
2. load active URL targets
3. prioritize due targets
4. crawl those targets
5. detect changed content
6. extract only changed/relevant content
7. update observations
8. run validation and matching
9. update source health
10. periodically run discovery for new candidate sources

A crawl failure must never be interpreted as zero promotions.

## Suggested starting cadence

```text
High-value promotion URLs:       15–60 minutes
Retailer/product pages:          1–6 hours
Official company catalogs:       6–24 hours
Recent news:                     1–6 hours
Source discovery:                daily/weekly, configurable
```

These are starting values, not hard-coded guarantees.

## Acceptance criteria

The multi-source architecture is accepted when:

1. A source can be registered without changing canonical promotion tables.
2. A source can be disabled without deleting historical observations.
3. A URL target can be scheduled independently from its domain.
4. A successful crawl is recorded even when zero promotions are extracted.
5. A failed crawl is not interpreted as zero promotions.
6. Changed content can trigger extraction while unchanged content can be skipped.
7. Multiple sources can produce observations for the same canonical promotion.
8. Conflicting regional prices remain separate when commercially material.
9. Source reliability is configurable and auditable.
10. The system can periodically discover candidate sources without automatically trusting them.
11. Normal runs primarily use the approved source/URL registry rather than restarting from unrestricted web search.
12. No collection mechanism circumvents authentication, CAPTCHA, paywalls or other access controls.
