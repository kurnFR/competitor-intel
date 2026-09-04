# SOURCE_STRATEGY.md — Multi-Source Discovery, Registry and Crawling Strategy

## 1. Purpose

The platform must not depend on a single promotion source. Hemat.id is only an initial source, not the permanent source of truth.

The system should discover, register, evaluate and continuously monitor multiple publicly available sources that can contain relevant FMCG competitor information.

The goal is:

```text
Discover sources once
      ↓
Register approved sources
      ↓
Evaluate source reliability + access rules
      ↓
Crawl according to source policy
      ↓
Persist evidence + observations
      ↓
Future runs crawl only eligible registered sources/URLs
      ↓
Re-discover periodically to detect new source pages
```

## 2. Source Classes

The source registry must support at least:

1. Official manufacturer/company websites
2. Official brand websites and campaign pages
3. Official retailer websites and weekly/catalog promotion pages
4. Modern trade websites such as supermarkets and hypermarkets
5. Convenience retail websites/apps where public content is accessible
6. Verified marketplace stores and product/promotion pages
7. E-commerce platforms where public pages are legally and technically accessible
8. Promotion/price aggregation sites
9. Established news/media websites
10. Public social/content pages where permitted
11. Local/regional modern trade and retail websites
12. Other approved public sources

Examples of discovery targets include company sites, Superindo, Alfamart, Indomaret, Hypermart, Tokopedia, Shopee, TikTok Shop and local retailers. These are examples of source candidates, not a guarantee that every platform can or should be crawled.

## 3. Important Access Rule

Only collect publicly accessible information in accordance with the website's terms, robots directives, applicable law and technical restrictions.

Do not bypass login controls, CAPTCHAs, paywalls, anti-bot controls or other access restrictions.

A source that cannot be collected compliantly should be marked `BLOCKED` or `MANUAL_ONLY`, not circumvented.

## 4. Source Registry

`source_registry` is the control plane for collection.

Minimum concepts:

```text
source
source domain
source type
owner/organization
base URL
source reliability
priority
crawl frequency
allowed status
access policy
adapter type
last discovery
last successful crawl
last failure
```

A source is not considered production-eligible merely because it was discovered by search or an LLM.

## 5. Source Lifecycle

```text
DISCOVERED
   ↓
CANDIDATE
   ↓
ASSESSED
   ↓
APPROVED
   ↓
ACTIVE
   ├── HEALTHY
   ├── WARNING
   ├── STALE
   ├── BLOCKED
   └── DISABLED
```

Sources can return to `CANDIDATE` or `DISABLED` after repeated quality/access failures.

## 6. Source Discovery

Discovery is a separate process from regular crawling.

### Regular crawl

Crawl already-approved source targets.

### Discovery scan

Periodically search for new candidate sources and new relevant URLs within approved domains.

The discovery process should use:

- search engines
- source sitemaps
- RSS/feeds where available
- site navigation
- category pages
- retailer promotion pages
- public product/category indexes
- known URL patterns

Discovery results must not automatically enter the canonical promotion dataset. They first enter the source/URL candidate queue.

## 7. URL Target Registry

The system should eventually maintain a URL-level registry in addition to the domain-level source registry.

Suggested concepts:

```text
source_id
url
canonical_url
page_type
category_hint
crawl_priority
crawl_frequency
is_active
last_crawled_at
last_success_at
last_content_hash
last_http_status
```

This enables the next run to focus on URLs that have previously produced useful information instead of repeatedly crawling the entire internet.

## 8. Adaptive Crawling

Not every URL needs the same frequency.

Recommended policy:

```text
High-value promotion page       frequent
Retailer weekly promotion page  frequent
Product page with stable data   moderate
Company product catalog         moderate
News article                     event/recent based
Historical page                  low frequency
Failed/blocked URL               backoff/manual review
```

The scheduler should prioritize URLs based on:

- previous promotion yield
- freshness needs
- source priority
- recent content changes
- upcoming/active promotion periods
- previous crawl success
- failure/backoff state

## 9. Content Change Detection

Before invoking expensive AI extraction, compare the new content hash with the previous successful version where practical.

If content is unchanged:

```text
crawl → hash comparison → no extraction required
```

If content changed materially:

```text
crawl → changed → extract → validate → persist observation
```

Do not assume unchanged HTML always means unchanged commercial data when the source uses dynamic content. Source adapters may define a more appropriate change detector.

## 10. Source-Specific Adapters

Use an adapter per source family where structure differs.

Examples:

```text
HematAdapter
RetailerAdapter
BrandWebsiteAdapter
MarketplaceAdapter
NewsAdapter
```

An adapter is responsible for discovery and extraction of source content, not for making final business decisions.

Canonical validation, geography normalization, entity resolution and ranking remain shared services.

## 11. Source Reliability

Reliability must be configurable and evidence-based.

Track operational metrics such as:

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

A source's reliability score may be adjusted based on observed quality, but changes must be auditable.

## 12. Source Priority

Source priority should consider both authority and commercial usefulness.

Suggested precedence for conflicting facts:

```text
Direct official promotion/retailer evidence
        > verified official store evidence
        > trusted promotion intelligence
        > established media
        > public social/other
```

This is a conflict-resolution aid, not permission to discard lower-tier observations. All useful observations remain available for audit.

## 13. Multi-Source Conflict Handling

When two sources report different values for the same product/promotion:

1. retain both observations
2. compare timestamps
3. compare source reliability
4. compare geographic scope
5. compare retailer/channel
6. determine whether they are actually different commercial activities
7. if unresolved and material, send to review

Never overwrite one source simply because another source arrived later.

## 14. Source-to-Canonical Flow

```text
Source Registry
      ↓
URL Target Registry
      ↓
Crawler
      ↓
Raw Crawl Document
      ↓
Extraction Observation
      ↓
Validation
      ↓
Geography + Entity Resolution
      ↓
Promotion Matching
      ↓
Quality Gate
      ↓
Canonical Promotion
```

The source layer must remain independently queryable.

## 15. Recommended Initial Rollout

Do not attempt to crawl every possible website on day one.

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

The source registry should make adding a new source a configuration + adapter task rather than a rewrite of the canonical database model.

## 16. What the Next Run Should Do

A normal scheduled run should NOT search the entire web from scratch.

It should:

1. load active approved sources
2. load active URL targets
3. prioritize due targets
4. crawl those targets
5. detect changed content
6. extract only changed/relevant content
7. update observations
8. run validation and matching
9. update source health
10. periodically run source discovery to find new candidate sources

This reduces cost, latency and unnecessary crawling while still allowing the system to discover new sources.

## 17. Source Discovery Cadence

Suggested defaults:

```text
Known high-value promotion URLs: 15–60 minutes
Known retailer/product pages:    1–6 hours
Official company catalogs:       6–24 hours
Recent news:                     1–6 hours
Source discovery:                daily/weekly depending on source class
```

These are starting values and must be configurable.

## 18. Acceptance Criteria

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
10. The system can periodically discover candidate new sources without automatically trusting them.
11. The next scheduled run primarily uses the approved source/URL registry rather than restarting from an unrestricted web search.
12. No collection mechanism bypasses access controls or other source restrictions.
