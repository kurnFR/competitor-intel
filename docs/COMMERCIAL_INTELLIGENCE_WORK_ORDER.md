# Commercial intelligence work order

Baseline reviewed: `master` at `19f1dd65ebf8d6e4960c04444dc7dc061dbb2a9a`.

## Release implementation

| Workflow | Entry point and behavior |
| --- | --- |
| Capture and review | Field observations accepts a transcription, optional source URL, JPEG or PNG, price, pack, dates, retailer, competitor and area. Draft text persists in the browser tab. A different Admin approves, rejects or returns it for correction. Corrected submissions retain their earlier reference. |
| Manage own pricing | Price comparison supports own SKU imports and per-SKU price history. Field observations also records retailer and region price periods. A comparison with both filters uses the latest applicable recorded period. Portfolio-wide reports use the general catalog price. Base-price history starts with the migration snapshot. |
| Compare products | Open a SKU's category search, inspect eligible evidence, then confirm or exclude a recurring comparison. Category and pack-size candidates are labeled. Server-side filters and exports use the same selected scope. The on-screen shortlist is capped while the export includes every matching offer. Conditional offers remain searchable. |
| Executive decisions | Insights displays current comparable-SKU coverage, price pressure, the largest exposures, recently observed category activity, source health, reviewed field coverage and response records. Viewer accounts can read and follow source evidence. Analysts can record a response, owner, due date and status. |
| Rollout | See the commercial intelligence rollout in `docs/DEPLOYMENT.md`. The production pilot requires an actual own catalog, approved retailer feeds and field evidence from the deployment market. |

## Business outcome

Marketing can start from an own SKU or category, find recent competitor offers, submit a store or flyer observation when coverage is missing, and compare offers within the relevant channel and area. The CEO has a read-only weekly view of the largest exposures, evidence coverage, and the actions Marketing is taking.

## Review findings

| Priority | Finding | Disposition |
| --- | --- | --- |
| P0 | The price index showed 100 with no matches and used only the display shortlist when matches existed. The pressure percentage included SKUs with no matching offers. Category discount cards could substitute an undercut for a discount. | Corrected in the initial patch. All comparable offers feed the index, undefined KPIs remain blank, and price gaps stay separate from discounts. |
| P0 | The README describes manual competitor entry, but the promotion router and templates expose no submission workflow. The current live-data gate requires website provenance and stored text evidence. | Add a separate reviewable field-observation intake and explicit manual provenance eligibility in work order 2. |
| P1 | The own SKU stores one regular price and one promotion window. Editing that row removes the previous value from the current catalog, and the row cannot represent simultaneous channel or regional offers. | Add effective-dated own price and promotion records in work order 2. |
| P1 | The comparison matrix filters some results in the browser after offers have already been trimmed, while summary cards come from the API query. Changing matrix filters can give a different scope from exporting the same view. | Move report filters ahead of shortlist generation in work order 3. |
| P1 | Own-product date-only CSV imports resolve to midnight UTC. Partial product updates validate only the incoming object before applying it to the stored record. | Normalize WIB campaign dates and validate the merged record before persistence in work order 3. |
| P1 | Own buy-X-get-Y offers need an explicit promo price to qualify as active, and the activity breakdown uses the raw own promo price while the matrix uses the effective price. | Use one mechanic-aware pricing rule across the matrix, breakdown and simulator in work order 3. |
| P1 | Existing Viewer accounts can open Insights, while the own-price comparison and its executive summary require Analyst access. Analyst access also permits own-product writes. | Provide read-only executive metrics and retain Analyst for the marketing workflow in work order 4. |

## Work order 1 · Correct the existing workflow

The patch adds category-only promotion lookup with optional product or brand text. Search uses eligible stored evidence and reports source coverage where the user can view it. It also corrects the executive comparison summary on the existing comparison page. Price pressure uses matched own SKUs as its denominator and compares competitor offer prices with our shelf price. The price index uses each matched SKU’s effective own price and every eligible comparable offer for that SKU.

Acceptance: a Wafer-only search finds eligible wafer offers and excludes other categories. A SKU with three offers still uses all three when the screen shows one. No match yields an unavailable index and pressure percentage. A competitor offer that undercuts us without a known discount does not populate the category discount card.

## Work order 2 · Capture evidence and version prices

1. Keep the own SKU master for SKU code, barcode where available, brand, category, subcategory, variant and pack size. Add append-only price and promotion intervals by SKU, channel, retailer or outlet, and area. Backfill existing records with their known scope and dates. Preserve unknown scope on older records.
2. From an own SKU or category watchlist, show matches and the latest successful source checks. Offer **Add field observation** from the no-result state and from the main promotion workspace. Allow a store photo, receipt, flyer or source URL with a transcribed offer, capture timestamp, retailer or outlet, area, product and pack, IDR prices, mechanic, eligibility conditions and stated dates. Keep unknown fields explicit.
3. Save drafts and submissions separately from published promotions. An Analyst submits and a designated reviewer approves, rejects or requests a correction. Record the submitter, reviewer, decision time, evidence and any superseded revision. Review should show possible duplicate web and field offers side by side. Approval links evidence to the existing offer or creates one, with retries leaving one published result.
4. Reuse the existing promotion evidence drawer, identity matching and conflict review. Extend the visibility rule to recognize approved field provenance. Keep reviewer status distinct from OCR or extraction confidence. Preserve both observations on a conflict and hide unresolved disputed values from the executive view.

Acceptance: an Analyst captures a field offer after a search miss. The Viewer cannot submit or approve. A reviewer approves the evidence and the same offer appears in category search, comparison and the BI feed. A later scrape of that offer adds evidence without increasing the unique offer count. A rejected record remains available to the review team.

## Work order 3 · Make comparisons and date handling reliable

Apply category, scope, outlet, channel, validity and search filters before counting, comparing, truncating or exporting. Match approved products by explicit SKU mapping where available, then use category, subcategory and comparable pack size as match signals. Label category-only matches as candidates. Give Marketing a way to accept or reject recurring match suggestions.

Use WIB date boundaries for Indonesian campaigns. Separate the offer’s stated dates, the observation time, and the latest verification time. Label undated observations as recently observed. For the initial pilot, normalize same-item multipacks and straightforward discounts to IDR per 100 g. Keep conditional member prices, minimum baskets, cashback and mixed bundles visible with conditions and exclude them from the default comparable set until their economics can be confirmed. Keep shelf-to-shelf and promo-to-promo gaps separately labeled.

Acceptance: screen, export and BI feed reconcile under the same scope. Test an offer through the end of its stated local day, future and expired campaigns, stale or failing sources, a qualifying buy-two-get-one offer, ambiguous bundle pricing and a partial edit that would reverse the date range.

## Work order 4 · Give the CEO a weekly decision view

Reuse the existing Insights page, Viewer access and BI feed. Build the weekly decision view against the same curated promotion and comparison definitions so the in-app and Tableau views reconcile. Allow drill-through from every alert or KPI to the underlying evidence.

| Widget | Decision it supports | Definition |
| --- | --- | --- |
| Priority SKU exposure | Which SKU and retailer should Marketing investigate first? | Most material verified price gaps by matching scope, with current own price, competitor offer, validity and match count. Add sales weighting only once internal SKU-level sell-out can be joined and validated. |
| Category activity | Where are competitors increasing promotional activity? | Distinct verified offers by category, channel and week, with comparable coverage for each period and a separate count of offers first observed that week. |
| Evidence coverage | How much confidence should leadership place in this view? | Matched own SKUs / tracked own SKUs, latest successful checks, stale sources, and verified web and field evidence counts. Distinguish a successful check with zero matches from an incomplete or failed check. |
| Response tracker | What is Marketing doing about it? | Evidence-linked observation, proposed response, owner, due date and status. Capture verified actions and outcomes separately from the initial observation. |

Pilot with one priority category, two agreed retailer channels, and a field team or analyst who can independently cross-check a sample of prices, pack sizes, promotion conditions and dates. The fresh reference seed used during verification produced zero configured sources. Approve and validate the pilot's source adapters before using live coverage as a KPI. Confirm the weekly dashboard and BI export reconcile on the pilot data before expanding to other categories. If internal sell-out or margin data is added later, measure outcomes separately from observed competitor activity and use an agreed baseline for impact analysis.
