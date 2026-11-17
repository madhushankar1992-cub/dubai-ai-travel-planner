# Dubai seed catalog and evidence review

Latest selected-source review: 15 November 2026. Dataset: `2026-11-15.2`; schema: `1.0`.

## Current Phase 2 acceptance

The bounded four-day example and its genuine hotel alternative now pass as
`validated_estimate` under explicitly accepted planning assumptions. There are
27 places, 11 accommodation products, 60 prices, 54 routes, 4 tariffs and 34
evidence records. Twenty routes have OSRM road-network support; the remaining
heuristics remain unsupported. Four recurring schedules have **estimated**
projections limited to the example dates, never exception-free guarantees.

See [the complete evidence and reproduction guide](phase2-example.md) and
`evaluation/phase2-result.json`. Meals and ticket/taxi fee reserves are visibly
estimated, opt-in spending allowances, not supplier quotes. Exact hotel snapshots
expire after one day; alternative dates/parties cannot reuse them. No new packages,
map datasets or page bodies are needed. The older undated sample stays partial.

The following review history describes earlier snapshots and their limitations.

## Lightweight evidence update, 15 November 2026

The seed retains 27 places, 9 accommodation options, 35 price records and 36
estimated routes. Evidence grows from 23 to 28 small attributed records. No page
bodies, photos, downloaded maps, new packages or additional environments are needed.
Run `python scripts/build_seed.py` to reproduce the seed, then `dubai-data import`
to activate it. `scripts/review_seed.py` contains this review's changes.

- [Kite Beach operator](https://solemio.ae/kite-beach/): public entry is free;
  parking, food, equipment and optional beach passes are separate. The zero-price
  record applies only to public entry, not those extras or swimming access.
- [Emirates Al Seef listing](https://www.emirates.com/uk/english/dubai-experience/activities/1025/al-se/):
  the waterfront visit is free; purchases and paid activities are excluded.
- [Dubai Mall](https://www.thedubaimall.com/en/plan-your-visit/opening-hours): retail
  hours Monday-Thursday 10:00-23:00 and Friday-Sunday 10:00-midnight. These are
  ordinary published hours, not dated exception-free operating windows.
- [Rove JBR](https://www.rovehotels.com/en/hotels/rove-jbr/): the FAQ limits a
  standard Rover Room to two people; its family room is separate. The standard
  room record does not inherit the generic widget's child allowance.
- [Rove La Mer Beach](https://www.rovehotels.com/en/hotels/rove-la-mer-beach/):
  the Rover Room widget permits two adults plus one child aged 4-16. Only the
  complete 6-12 input band is accepted; crossing bands still need clarification.
- [Rove beach offer](https://www.rovehotels.com/en/offer/beach-staycation/): directly
  rechecked. AED 399 remains a per-room/night starting rate with breakfast for
  6 October-30 November 2026. Service, municipality, VAT and tourism charges
  remain excluded. The upper bound is unknown. The booking page could not be
  inspected because browser access was unavailable; no final quote was obtained.
- Dubai Frame and Jumeirah Mosque facts were directly rechecked and retain their
  existing prices and hours. Other sources retain their original review dates.

`dubai-data coverage --on-date 2026-11-20` checks price applicability and counts
only matching, fresh dated opening windows. Omitting the date does not make dated
offers usable. Price lookups return `unavailable` when no product applies, while
retaining records and warnings for inspection. The catalog UI exposes the date
selector, accommodation records and the actual price/occupancy source links.

**Earlier `2026-11-15.1` acceptance was open:** the four-day sample needed at least one
fee-inclusive bounded quote covering its three nights and party, reviewed
date-specific venue windows and usable connecting-route evidence. Its remaining
meal costs also prevent a complete trip budget. A public starting rate is not a
bounded quote; a property's room limit is not availability. No estimate was
promoted to verified evidence merely to pass acceptance. Broader catalog gaps
need not all be filled before a narrowly supported scenario can pass.

The sections below describe the earlier seed review and its retained limitations.

This is a starter catalog for the four-day demonstration, including alternatives.
It is not a complete inventory or a set of guaranteed bookable offers. Expansion
to the research targets is future editorial work, not an implemented capability.

## Collected facts and sources

| Source | Retained information | Verification and limitations |
| --- | --- | --- |
| [Dubai Frame](https://www.dubaiframe.ae/en/plan-your-visit) | Adult admission AED 50; ages 3-12 AED 20; under 3 free; published hours 08:00-21:00 | Direct official-page check. Special-date hours and booking fees still need confirmation. No date-specific opening guarantee. |
| [RTA nol fares](https://rta.ae/wps/portal/rta/ae/public-transport/Nol-Fares) | Silver-card fares AED 3, 5 and 7.50 by zone tier | Official indexed table checked; direct fetch timed out. These prices do not establish a zone path, transfer eligibility or departure schedule. |
| [Ravi menu](https://ravirestaurants.ae/menu/) | Selected meal-box choices AED 18, 22 and 27 | Direct page check. Only those products; branch applicability, taxes and serving assumptions remain unresolved. |
| [Rove offer](https://www.rovehotels.com/en/offer/beach-staycation/) | Starting offer AED 399, relevant Dubai properties only | Official indexed offer; direct retrieval unavailable. No upper bound or availability guarantee. Indexed terms cover 6 October-30 November 2026 and exclude service, municipality, VAT and tourism charges; operator reconfirmation is required. |
| [Visit Dubai cultural locations](https://www.visitdubai.com/en/articles/dubais-top-11-cultural-locations) | Cultural candidates; Alserkal general entry free, activities separate | Official reference and indexed factual check. Individual venue hours and ticket products remain separate. |
| [Visit Dubai neighborhoods](https://www.visitdubai.com/en/explore-dubai/dubai-neighbourhoods) | Six accommodation search areas | Official reference; no occupancy, hotel quote or inventory implied. |
| [Al Seef](https://soukalseef.ae/en/discover/attractions), [Kite Beach](https://www.visitdubai.com/en/places-to-visit/kite-beach), [Arabian Tea House](https://www.visitdubai.com/en/restaurants/arabian-tea-house) | Place identity and location context | Official references checked; original short annotations only. Unknown admissions, menu prices and access details remain null. |

Additional inherited identity references remain listed individually in the source
registry. They were not all re-fetched during this implementation. Recheck them
before treating the catalog as operational travel guidance. No retrieved webpage
can authorize tools, modify policies, or become executable instructions.

## Original editorial methods

### Public-source enrichment, version 2026-11-05.3

The catalog now contains 27 places, 35 price records and 23 evidence records.
The reproducible additions are in `scripts/enrich_seed.py`; no network requests,
API keys or Google services are used by the seed builder or application.

- [Published museum tariff](https://dlp.dubai.gov.ae/Legislation%20Reference/2024/Administrative%20Resolution%20No.%20%28256%29%20of%202024%20Approving%20Ticket%20Prices%20for%20the%20Etihad%20%26%20Shindagha%20Museum.html): individual admission AED 50 for Shindagha and AED 25 for Etihad. Student, group and trade discounts require distinct eligibility. Only standard adult products are used in costing; fees remain unconfirmed.
- [Shindagha operator listing](https://experiences.visitdubai.com/productDetail/84101): daily 10:00–20:00, last entry 19:00. Its AED 35 adult product is a separate channel/product from the published individual tariff; it does not overwrite that tariff. Prices must be reconfirmed for the chosen product.
- [Jumeirah Mosque public visits](https://www.jumeirahmosque.ae/mosque-visit-public/): AED 55, Saturday–Thursday sessions at 10:00 and 14:00, registration 30 minutes earlier. Fixed sessions are retained as prose, not converted into continuous admission windows. Child eligibility and fees need confirmation.
- [Rove Dubai Marina](https://www.rovehotels.com/en/hotels/rove-dubai-marina/): Rover Room capacity is two adults and one child. The widget says ages 4–16 while room prose says under 16; only the application's 6–12 band is fully supported by both. Other child bands require clarification. This establishes room capacity, not availability or a bounded quote.
- [Al Fanar operator menu](https://www.alfanarrestaurant.com/menu): the default Al Barsha Pond Park menu lists a small Mixed Seafood BBQ serving one at AED 78. This new dining candidate retains a single selected product, not a restaurant-wide meal range. Branch differences, additional orders and fees remain explicit.

New candidates lack verified coordinates; none were fabricated. Published ordinary
hours do not prove exceptions for a future travel date. No date-valid opening
windows or verified road/walking routes have been added. Failed direct retrievals
of MBR Library and Alserkal pages were not used to promote their facts.

`dubai-data coverage` produces an evidence-aware gap inventory. Its checked-in
snapshot is `evaluation/data-coverage.json`; counts describe catalog coverage,
not complete party eligibility or itinerary feasibility. All nine accommodation
options still need bounded, dated, fee-inclusive quotes. Free public reference
pages cannot establish live room availability for an unspecified trip.

### Routing and scheduling assumptions

Coordinates are approximate editorial centroids, not surveyed entrances. Visit
durations are allowances selected for planning experiments. Route ranges use
great-circle centroid distance multiplied by 1.5 and assumed speeds of 4 km/h
(walk) or 25 km/h (taxi), a minimum of 10 minutes and upper bound
`max(lower + 15, ceil(lower * 1.8))`. These are heuristic intervals, not observations.
They already include an uncertainty allowance, so the scheduler does not add a
second travel contingency. `feasibility_supported=false` blocks validation of
every such route. Missing connecting legs remain missing.

The scheduler adds a visible 15-minute activity buffer, a 45-minute meal/rest slot,
and a provisional 60-minute reservation when a route is absent. That reservation
never satisfies the missing-route rule. It is a layout allowance only.

The costing service extends quantities with Decimal arithmetic and applies a
separate 10% budget contingency. Values are summed before display rounding to two
decimal places using ROUND_HALF_UP. A starting rate or unknown mandatory fee
prevents a complete total. Selected meals do not cover all daily meals; missing
meals remain budget gaps. These defaults are configurable service arguments.

## Rights, provenance and freshness

The source registry authorizes only selected atomic facts, reference links and
original editorial annotations for this project. It does not assert that entire
websites, photos, descriptions, reviews or menus have a redistribution licence.
No page bodies or images are copied into the dataset. Policy allowlists are field
specific; unreviewed sources and disallowed persistence/export operations fail.

Review timestamps use the review date at 00:00 UTC because exact historical
retrieval times were not retained; source update dates remain null. Evidence
records state the method and source. A review date is not an effective travel
date. Date-limited offers are unusable for undated requests. Sources become stale
according to their recorded maximum age and must be rechecked.

Price records intentionally include null values. All accommodation area prices
remain unknown; the hotel starting offer does not supply market-wide nightly
ranges. Accessibility is unknown. Structured date-valid operating windows, usable
route evidence, confirmed occupancy and complete taxes/fees remain the principal
data gaps. The project can demonstrate selection, costing and validation while
honestly returning partial outcomes.

Synthetic successful routes and test prices live only in tests. No synthetic
entity or fabricated market quote is published as a real recommendation.
