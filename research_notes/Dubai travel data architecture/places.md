# Dubai place, attraction, restaurant and open-data acquisition

## Which sources can supply places and operational facts?

### Takeaway
Recommendation: start with a small, independently authored, source-traceable JSON/SQLite catalog; add Google Places on demand or OSM imports as separate adapters. Official websites remain verification sources, but public readability is not a reuse licence. Research reference date: 2026-11-04; no authenticated provider calls or Dubai coverage benchmark performed.

### Cited Findings
- Google Places (New) provides identifiers, display names, coordinates, addresses, types, business status, website, opening hours, ratings and price-level fields. Fields may be absent. Current opening hours cover seven days from the request date; regular hours are a recurring schedule. `OPERATIONAL` is not equivalent to open now. Price level is categorical, not an AED meal quote. [Place resource](https://developers.google.com/maps/documentation/places/web-service/reference/rest/v1/places)
- Billing must be enabled; API key or OAuth is required. Pricing is usage/SKU based, and requesting a higher-tier field raises the request's billed tier. Use explicit field masks, bounded search and details only for finalists. Do not cite the expired February 2025 monthly credit as current. [Usage and billing](https://developers.google.com/maps/documentation/places/web-service/usage-and-billing)
- Places content cannot be indiscriminately cached, indexed or stored. Place IDs are an explicit exception. Attribution is required, including applicable third-party authors/providers; map presentation of Places results requires Google Maps. Separate API results from the permanent local catalog and from OSM map presentation. Public terms/privacy notices are required for an application using Places. [Policies](https://developers.google.com/maps/documentation/places/web-service/policies)
- Overpass provides queries over OSM rather than geocoding. Public resources can reject load with 429/504 and are not an availability guarantee; larger usage should use self-hosted/managed service. [Overpass operator manual](https://dev.overpass-api.de/overpass-doc/en/preface/commons.html)
- OSM uses ODbL with attribution/share-alike considerations for databases; displaying OSM-derived content needs attribution. Keep provenance and review the applicable derivative/collective database conditions before distributing a combined database. [OSMF licensing FAQ](https://osmfoundation.org/wiki/Licence_and_Legal_FAQ), [attribution guidance](https://osmfoundation.org/wiki/Attribution_Guidelines)
- OSM supports structured `opening_hours` tags; interpret rather than compare human-readable strings. [Tag specification](https://wiki.openstreetmap.org/wiki/Opening_hours)
- Public Nominatim has an absolute 1 request/second maximum per application, identifying User-Agent/Referer, attribution and caching expectations. No autocomplete or systematic whole-area POI harvesting. Its policy now explicitly requires deliberate developer responsibility and disallows embedding it as a generic service in AI/no-code generated platforms. Prefer pre-geocoded catalog or a managed/self-hosted geocoder by default. [Public Nominatim policy](https://operations.osmfoundation.org/policies/nominatim/)
- Visit Dubai restricts reuse to personal noncommercial uses except as permitted; its terms prohibit using content to maintain a separate publication/site without approval. Do not scrape its articles/images into an app or vector database on the assumption that tourism content is open data. Link to it and seek permission for ingestion. [Visit Dubai terms](https://www.visitdubai.com/en/terms-of-use)

### Inferences
- Suggested OSM import fields: element type/id, name variants, geometry/centroid, category, address, website, optional cuisine/opening_hours/accessibility tags. Missing tags mean unknown, never false; manually verify Dubai POI coverage and multilingual duplicates.
- Suggested MVP: 30–50 attractions, 15–25 dining choices, 6–10 accommodation areas. These are project sizing recommendations, not measured provider coverage. Author descriptions and preference/crowd tags locally, label them heuristics, and keep objective facts with individual sources.
- API `priceLevel` and reviews cannot establish an exact meal price, absence of crowds, dietary safety or ticket inventory. Crowd avoidance should be a curated preference heuristic with visible uncertainty.
- Provider policy belongs in adapter configuration: allowed persistence, TTL, display attribution, permissible LLM processing, export and map constraints. Do not store raw Google results in checkpoints/logs by default; field-level data minimization also applies to traces and benchmark fixtures.

### Gaps
- No live Google/OSM Dubai sample was measured; completeness, language quality, accessibility/dietary tags, and field fill rates remain pilot tasks. No Google contract-specific permission for feeding content to an LLM was established; verify applicable terms before enabling that path.

## How can official, manually curated and government data be acquired safely?

### Takeaway
Use original operator pages and permitted downloads to verify operational facts and costs. Treat Dubai government catalogs as optional discovery sources until a specific dataset's schema, freshness, licence and credentials have been checked.

### Cited Findings
- An indexed Dubai Pulse dataset page documents API key/secret issuance on dataset grant/package purchase, client-credentials token exchange and a token on calls; it also lists downloadable CSV. This establishes a portal mechanism, not tourism dataset availability or free API entitlement. [Dubai Pulse dataset/API guidance](https://gslb.dubaipulse.gov.ae/data/dld-registration/dld_projects-open?page=8)
- UAE government directs tourism-data users to DET and Dubai Statistics Center among other official sources. Such statistics must not be assumed to contain operational POIs, tickets or opening hours. [Official tourism-data directory](https://u.ae/en/information-and-services/visiting-and-exploring-the-uae/open-government-data-tourism-in-the-uae)
- Freshness conflict observed: the Museum of the Future origin plan-your-visit page shows operating hours and a ticket tariff, while the canonical main site currently states temporary closure. Prioritize canonical operational notices, retain the conflict, and do not interpret an old tariff as bookable availability. [Canonical museum site](https://museumofthefuture.ae/en), [origin visit information](https://prod-origin.museumofthefuture.ae/en/plan-your-visit)

### Inferences
- Acquisition options: manually author factual records from permitted references; import operator-provided CSV/JSON; parse authorised HTML/JSON-LD; extract permitted PDF menus/tariffs with page references; OCR scans only with verification; accept user uploads with rights/format validation; negotiate direct operator feeds; collect explicitly consented feedback as unverified suggestions. These are design options, not confirmed existing integrations.
- Source registry fields: source_id, owner, canonical URL, acquisition method, terms URL, licence/access state, allowed fields/use, auth method, frequency, contact/approval evidence and retention policy. Per value retain source ID, observed_at, valid_from/to, confidence, currency, price unit, tax inclusion, age band, ticket option, status and evidence reference. Store raw evidence only where permitted.
- Refresh proposal (not provider guarantees): operational notices/hours and shortlisted ticket prices before planning when permitted; manually reviewed prices weekly; relatively stable names/coordinates monthly; holiday/Ramadan schedules explicitly rechecked. Date-specific tickets need date/time/product/party context. Stale records should be marked, skipped or replaced; absence of data must never become zero cost.
- Web extraction workflow: check source permission and applicable terms first, honor crawl controls and rate limits, restrict domains/URLs, fetch bounded content, reject access-control bypasses, parse facts into schema, validate with human review for conflicting/critical fields, publish a versioned catalog. Robots permission alone does not grant reuse rights. Treat website text as untrusted data, never agent instructions.
- Keep government source ingestion conditional on an actual dataset review; record update cadence, geographic granularity and null patterns. Historical visitor totals can inform context but not establish today's crowd level.

### Gaps
- data.dubai returned a request-rejection page; Dubai Pulse homepage and licence PDF fetch timed out during research. Therefore no claim of a working tourism endpoint, current dataset licence, quota, cost or SLA is verified. The indexed API mechanism above must be retested before implementation. Exact attraction/menu prices are deliberately excluded from proposed seed data pending canonical verification and permitted reuse.

## What licensed alternatives and rollout controls are appropriate?

### Takeaway
Foursquare and Viator are credible optional commercial/partner paths, subject to account terms, access tier and coverage testing. Neither is necessary to demonstrate five agents or compare LangGraph and CrewAI.

### Cited Findings
- Foursquare's current Places documentation supports service keys in `Authorization: Bearer` with an API version header. Its migration notice says legacy v3 deprecation was scheduled May 15, 2026; use the new Places API and verify account entitlement. [Authentication](https://docs.foursquare.com/fsq-developers-places/reference/authentication), [migration notice](https://docs.foursquare.com/developer/reference/upcoming-changes)
- Foursquare pricing is usage/field tier based. Its pricing page contains inconsistent free-call marketing text versus the current tier table; do not hard-code a free allowance without account verification. [Pricing](https://foursquare.com/pricing/)
- Viator API offers products, options, logistics, price/availability data with endpoint availability varying by partner level, authenticated using `exp-api-key`. Basic access has narrower nontransactional endpoints; full access unlocks bulk/delta paths. [Technical reference](https://docs.viator.com/partner-api/technical/)
- Viator Basic access is self-service; higher access requires approval/certification. The affiliate model can direct customers to Viator rather than add booking to this project. Partner use and content rights remain governed by its program terms. [Access levels](https://partnerresources.viator.com/travel-commerce/levels-of-access/), [program terms](https://partners.viator.com/static/docs/Viator-Partner-Program-Terms-en_EN.pdf)

### Inferences
- Rollout: P0 curated verified catalog and deterministic mocks; P1 optionally enable Google Places or OSM discovery using adapter policy; P2 assess one government dataset, managed geocoder, Foursquare or activity partner feed only where it fills a demonstrated gap. Exclude booking/payment implementation.
- For each provider pilot, sample 20 known Dubai locations across neighborhoods; measure match rate, coordinates, category precision, hours completeness, closures, price availability, latency, cost and licensing fit. These are proposed acceptance checks, not measured results.
- Resolve entity conflicts using stable provider IDs plus curated crosswalks, spatial/name review and source priority appropriate to each field. Do not overwrite canonical records blindly. Keep Google identifiers separate from independently acquired facts.
- On timeout, 429, unavailable keys or quota exhaustion: bounded retries/backoff, circuit breaker, then vetted local fallback; propagate source_mode and freshness warnings to both frameworks. Benchmark both frameworks on the same permitted frozen dataset/snapshot; do not make repeated paid calls per agent or silently compare different source versions.
- Evaluate Foursquare/Viator storage, redistribution, attribution, AI processing and refresh requirements from the actual subscribed agreement before persistence. Partner API availability does not itself grant unrestricted rights.

### Gaps
- No provider account is configured, no access tier approved, and no paid-provider Dubai coverage benchmark or current negotiated licensing terms were tested. Additional alternatives such as HERE, TomTom, Geoapify, Wikidata/Wikivoyage and direct DMC/restaurant partnerships are candidates for future due diligence, not researched recommendations in these notes.
