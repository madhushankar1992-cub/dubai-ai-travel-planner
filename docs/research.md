# Dubai Travel Data Research: Free and Open Sources

**Provider scope:** Use the approved local catalog, licensed open datasets, and separately reviewed no-charge sources only. External capabilities remain disabled until their access, quota, coverage, and reuse checks pass.

**Provider scope confirmed: 15 November 2026.** Paid travel-data integrations are
excluded from the research shortlist and implementation backlog. Trial credits,
billing-enabled free tiers and metered endpoints with possible charges are not
eligible alternatives. Do not add their SDKs, credentials, billing setup or
fallback calls. Retained options are the local catalog, licensed downloads,
open-source tools and services with a verified no-charge path for this project.
If none qualifies, retain local estimates or report missing evidence.

**Research date: 4 November 2026. Scope updated to LangGraph and no-charge travel data.** This report supports the [problem statement](problemstatement.md) and [system architecture](architecture.md).

Build the Dubai AI Travel Planner around an independently authored, versioned local catalog. Enrich it through licensed open datasets and eligible free services. Paid travel-data APIs, subscriptions, commercial partner integrations, and automatic billable upgrades are excluded. The five agents use shared LangGraph state and data tools.

No-charge access does not establish reuse rights, unlimited capacity, a service guarantee, or complete Dubai coverage. Optional integrations must pass eligibility, quota, licence, and coverage checks. On quota exhaustion or unavailable access, use reviewed local data or report missing evidence. Model inference and hosting are separate resource decisions; local models and local deployment can avoid dependence on hosted inference. Self-hosted open-source services still require hardware and maintenance.

The retained source findings below are documentation research, not authenticated service testing. Government dataset access, a current usable Dubai transit feed, and a live crowd feed remain unverified.

## 1. Start with reusable facts and add live observations selectively

### Match each planning decision to its evidence

The Destination Research Agent needs place identities, categories, coordinates, interests, operating information and dining options. Logistics needs accommodation areas, route durations, travel modes and service constraints. Budget needs AED amounts with units, party assumptions and inclusions. Review needs provenance and freshness as much as the values themselves: a plausible number without its price basis cannot establish budget compliance. The Orchestrator should obtain data through shared application services so agents do not duplicate requests, exhaust free quotas, or use inconsistent observations.

The following matrix is the proposed acquisition plan. Each optional source must be usable without paid calls or billable overages before it can be enabled.

| Requirement | Default acquisition | Optional no-charge enhancement | Limitation and fallback |
| --- | --- | --- | --- |
| Attractions and neighborhoods | Original catalog with factual references | OpenStreetMap/Overpass; licensed government download | Missing fields remain unknown; return reviewed local candidates |
| Descriptions | Independently written summaries and official reference links | Explicitly reusable tourism/operator material | Public readability does not permit copying content |
| Restaurants | Curated names, cuisines, coordinates, and AED ranges | OSM tags and permitted menu information | Dietary/accessibility claims need separate evidence |
| Hours, closures, tickets | Manually reviewed operator facts with review dates | Permitted structured downloads or extraction | Check date/product/age band; exclude time-critical visits if evidence is insufficient |
| Coordinates | Pre-geocoded records with source attribution | Bounded OSM import or local geocoder | Distinguish entrances from building centroids |
| Routes | Reviewed area-to-area duration intervals | Local OSRM/openrouteservice engine; verified eligible free endpoint | Road profiles do not establish transit; retain estimated buffers |
| Transit fares | Official RTA tariff references and reviewed rules | Reusable official no-charge download | Zones, card classes, transfer conditions matter |
| Transit schedules | Reviewed planning assumptions and official links | Licensed no-charge GTFS after verification | No confirmed current feed or realtime service; no invented departures |
| Accommodation | Area recommendations and dated nightly ranges | Permitted manually checked hotel information | No live inventory or availability guarantee |
| Meals and incidentals | Curated ranges with per-person/serving basis | Permitted operator menus | Unknown charges are explicit, not zero |
| Weather | Optional eligible Open-Meteo free forecast | Locally stored permitted seasonal guidance | Outside forecast window, label seasonal guidance or omit |
| Crowds | Explained editorial heuristics | No live feed assumed | Avoid guarantees; ratings and review counts are not crowd measurements |
| Preferences | User request and visible assumptions | Consented user corrections | Feedback creates review candidates, not automatic verified facts |
| Government context | Dataset-specific access/licence review | Data.Dubai / Dubai Pulse / official statistics | Only no-charge reusable datasets; historical totals do not establish current venue conditions |

### Make local data a deliberate product asset

A practical seed target is **30–50 attractions, 15–25 dining choices and 6–10 accommodation areas**. These are proposed project sizes, not measured source coverage. Authors should write their own descriptions, retain references for factual fields, and explicitly label estimated visit durations, preference tags and crowd guidance. CSV is convenient for review, JSON for nested records and Git diffs, and SQLite for normalized runtime queries. These are storage and transport formats, not independent evidence sources. Keep editorial source files under version control and generate the runtime database through a repeatable import.

User uploads can supply personal recommendations, budgets or licensed catalogs. Validate file type, size, schema, currency and rights declarations before import; treat uploaded descriptions as untrusted data. Consented feedback such as “this entrance was closed” should create a review candidate rather than immediately overwrite a verified record. Voluntarily supplied no-charge CSV or JSON files from operators may supplement the catalog when reuse rights, update cadence, and expiry are clear. No commercial feed or partner relationship is assumed.

## 2. Acquire places, prices and government data under explicit permissions


### OpenStreetMap supports a different ownership and operating model

Overpass queries OSM features and tags. A bounded import can collect `tourism`, `amenity=restaurant`, names, coordinates, websites, cuisines and optional accessibility/opening-hours tags for a selected Dubai area. Store element type and ID because an OSM node, way and relation can have overlapping numeric identifiers. Missing tags mean unknown. Parse `opening_hours` using a compatible parser and retain the original expression; simple string comparison cannot resolve exceptions and schedules. ([Overpass public-instance guidance](https://dev.overpass-api.de/overpass-doc/en/preface/commons.html), [opening-hours specification](https://wiki.openstreetmap.org/wiki/Opening_hours))

Public Overpass resources can reject load and do not provide an application SLA. Use small, infrequent imports with retry limits; reduce import frequency or use a locally hosted instance if usage grows; do not switch to a paid service. OSM data carries ODbL obligations, including attribution and database-related share-alike considerations. Separate source provenance and review derivative/collective database treatment before distributing a combined catalog. Open-source tooling does not remove hosting costs or underlying data-license obligations. ([OSMF licensing FAQ](https://osmfoundation.org/wiki/Licence_and_Legal_FAQ), [attribution guidance](https://osmfoundation.org/wiki/Attribution_Guidelines))

**Do not make the public Nominatim endpoint the default geocoder.** Its public service policy imposes an absolute one-request-per-second application maximum, identification and attribution requirements, prohibits autocomplete/systematic POI harvesting, and places specific responsibility on developers integrating it through AI/no-code platforms. Pre-geocode the local catalog or use a locally hosted geocoder with suitable data and capacity. ([Public Nominatim policy](https://operations.osmfoundation.org/policies/nominatim/))

### Official references still require source-specific access review

Visit Dubai's terms restrict reuse and prohibit using its content to maintain a separate publication or website without permission. Link to relevant pages and write original descriptions; do not ingest its articles or images into the app or a retrieval index on the assumption that tourism material is open data. Authorized operator downloads, licensed extracts and negotiated feeds are more straightforward ingestion candidates. ([Visit Dubai terms](https://www.visitdubai.com/en/terms-of-use))

For permitted website extraction, register the owner, canonical URL, terms, allowed fields and retrieval cadence before implementing a fetcher. Respect crawl controls, rate limits and access restrictions; robots permission alone does not grant content reuse rights. Parse bounded HTML/JSON-LD into factual fields instead of retaining entire pages by default. Permitted PDF menus or tariffs can be extracted with page references; scanned documents need OCR followed by manual verification of prices and dates. Preserve raw evidence only when allowed. A canonical closure notice should override an older tariff page for operating status, while retaining the conflict for audit. The research encountered this type of inconsistency between a museum's main site and an origin visit-information page; it illustrates a validation risk, not a permanent statement about that venue. ([Museum canonical site](https://museumofthefuture.ae/en), [visit-information page](https://prod-origin.museumofthefuture.ae/en/plan-your-visit))

Dubai Pulse documentation on an indexed dataset describes downloadable CSV and an API access process involving key/secret issuance after dataset access, client-credentials token exchange and authenticated calls. This demonstrates a portal mechanism, **not a verified tourism endpoint, free entitlement or current SLA**. Data.Dubai access was rejected during research; some Dubai Pulse pages and licence material timed out. Government tourism directories point to official statistical sources, but those statistics must not be treated as a current POI, ticket or opening-hours catalog. ([Dubai Pulse dataset/API guidance](https://gslb.dubaipulse.gov.ae/data/dld-registration/dld_projects-open?page=8), [UAE tourism-data directory](https://u.ae/en/information-and-services/visiting-and-exploring-the-uae/open-government-data-tourism-in-the-uae))


## 3. Use open routing, curated accommodation, and eligible free forecasts

### Route estimates and open-source engines

Start with reviewed area-to-area intervals that include transport mode, estimation method, observation date, and uncertainty. These are planning estimates, not measured live traffic. Straight-line distance alone cannot establish a road route, transit connection, walking access, or fare. If a critical leg lacks sufficient evidence, return a partial itinerary instead of claiming schedule validation passed.

OSRM provides route and table services for the profiles present in the deployed routing graph. Changing a URL profile does not build a walking or cycling graph. A local deployment can use permitted OSM data and avoids a per-call provider bill, but requires graph preparation, updates, and computing resources. A public demonstration endpoint is not assumed to be a production dependency. ([OSRM API](https://project-osrm.org/docs/v5.9.1/api/))

openrouteservice is another open-source routing option. Its API supports directions and its backend documents public transport with GTFS input. This does not verify hosted Dubai transit coverage. Use the local engine or enable a hosted endpoint only after checking that the intended use is eligible for no-charge access, quotas are known, and no billable overages can occur. If those checks cannot be completed, keep the adapter disabled and use curated estimates. No particular current hosted free allowance is assumed. ([openrouteservice API](https://openrouteservice.org/dev/), [backend data requirements](https://giscience.github.io/openrouteservice/run-instance/data))

Filter and geographically cluster candidates before requesting routes. Validate only shortlisted adjacent legs; inspect errors individually rather than converting an absent result to zero duration. Recompute affected legs after changing locations, times, or modes. Preserve routing profile, map version, source, and duration assumptions in every result.

### Official public transport information

RTA's official fare rules depend on zones and card class and describe intermodal transfer conditions, including a 30-minute transfer window. Its published table also specifies journey duration and transfer limits. Transcribe the applicable table with a review date and distinguish card purchase cost from usable travel balance. Do not infer a transit fare from straight-line or road distance. ([RTA nol fares](https://rta.ae/wps/portal/rta/ae/public-transport/Nol-Fares))

RTA points to Dubai Pulse for open-data contributions. The candidate [Dubai GTFS dataset page](https://www.dubaipulse.gov.ae/data/rta-public-transports/rta_gtfs-open) timed out during research, so download access, licence, no-charge eligibility, and current service dates remain unverified. Enable an import only after these checks succeed. Validate stop coordinates, agency timezone, calendar exceptions, service coverage, and expiry. Static GTFS describes scheduled services, not live vehicles or disruptions; no official realtime feed was verified. Until then, use official reference links and disclosed planning assumptions. ([RTA open data](https://rta.ae/wps/portal/rta/ae/home/open-data?lang=en))

### Accommodation and meals use curated price evidence

Recommend accommodation areas using budget band, nearby interests, and transport access. Maintain independently researched nightly ranges with a date, occupancy basis, source reference, and tax/fee inclusion status. Permitted operator facts can update these ranges through manual review or approved extraction. They do not establish live room inventory, availability, or a guaranteed quote.

Normalize check-in/out, nights, rooms, adults, children, currency, and included charges. For a per-room/night rate multiply rooms by nights; for a per-room/stay amount multiply rooms only; for a whole-party/stay total use quantity one. Never multiply a stay total by nights again. Missing mandatory fees remain unknown or an explicitly justified estimate. Accommodation uses nights, not itinerary days.

For meals, store per-person/meal or group-bill units, serving assumptions, and known exclusions such as drinks. A broad price category is not an exact AED meal cost. Unknown menu prices must not become free meals. Price ranges and contingency should remain visible to the Budget and Review Agents.

### Weather supports near-term scheduling; crowd avoidance remains heuristic

Open-Meteo offers a seven-day forecast by default and up to sixteen days, with variables such as apparent temperature, precipitation probability and wind. A typical request is `GET https://api.open-meteo.com/v1/forecast?latitude=25.2048&longitude=55.2708&hourly=apparent_temperature,precipitation_probability&timezone=Asia%2FDubai&forecast_days=16`. This is an illustrative request shape, not a fetched forecast. Request only the relevant dates and fields, and retain retrieval time and available model metadata. For dates outside the available window, provide explicitly labelled seasonal guidance or omit weather optimization. ([Forecast documentation](https://open-meteo.com/en/docs))

Free hosted access is noncommercial, with published limits of 600 calls/minute, 5,000/hour and 10,000/day and no uptime guarantee. Use only the eligible free service; large requests can count as multiple calls. Enforce shared limits and disable the integration if the intended use is ineligible or quota is exhausted. Fall back to permitted local seasonal guidance or omit weather rather than enabling a paid plan. Data attribution under CC BY 4.0 and permission to use the hosted service are separate requirements. ([Pricing and access](https://open-meteo.com/en/pricing), [licensing](https://github.com/open-meteo/open-meteo))

No verified live crowd feed is included. Use explicit heuristics based on venue guidance, permitted event information, and conservative time-of-day assumptions, with the basis and confidence visible. Review counts, ratings, and historical tourist totals are not live crowd measurements. The system can recommend times likely to be quieter but must not promise crowd avoidance.

## 4. Normalize evidence before agents reason about it

### A shared acquisition pipeline prevents contradictory plans

The recommended pipeline is `source registry → permitted acquisition → staging validation → normalization → entity matching → field conflict review → versioned publication → shared retrieval tools`. External observations should enter a separate policy-controlled cache instead of automatically becoming permanent local facts. The registry records owner, canonical URL, acquisition method, licence/access status, permitted fields and uses, authentication type, refresh policy, retention/export rules, attribution requirements and approval evidence where applicable. A disabled or unapproved source must not be silently enabled by an agent.

Normalize coordinates to an agreed latitude/longitude convention, currency to explicit ISO codes, durations to minutes, and local schedules to `Asia/Dubai` with timezone-aware timestamps. Treat monetary values as decimal quantities with units such as per adult, per meal, per room/night or whole stay. Prefer AED source values for the MVP. If later converting currencies, add an authorized exchange-rate source, rate timestamp and rounding policy; conversion must not be silently improvised by the language model.

Use internal entity IDs and separate provider-ID crosswalks. Candidate duplicate detection can combine normalized names, Arabic/English aliases, proximity and operator URLs, but a human should resolve uncertain matches. Two branches of a restaurant are not duplicates merely because their names match; an attraction entrance and its building centroid can require distinct coordinates. Field-level source priority should depend on the fact: an operator closure notice can outrank third-party recurring hours, while a date-specific licensed ticket quote can outrank a general historical range. Preserve conflicting observations instead of overwriting evidence without explanation.

### Store provenance per field and distinguish missing from zero

The following JSON is **illustrative schema data only**. It does not describe an actual Dubai attraction, live price or fetched observation. Nulls deliberately show unresolved values; a schema example must not become a plausible-looking production fixture.

```json
{
  "entity_id": "illustrative_place_001",
  "entity_type": "attraction",
  "name": "Illustrative venue — not a real recommendation",
  "coordinates": null,
  "timezone": "Asia/Dubai",
  "provider_ids": {},
  "fields": {
    "admission": {
      "value": null,
      "currency": "AED",
      "unit": "per_adult",
      "tax_included": null,
      "product": null,
      "valid_from": null,
      "valid_to": null,
      "source_id": "illustrative_source",
      "source_url": null,
      "observed_at": null,
      "evidence_type": "unknown",
      "confidence": null,
      "review_status": "pending"
    }
  },
  "crowd_guidance": {
    "level": "unknown",
    "basis": "No verified crowd observation",
    "evidence_type": "unknown"
  },
  "license_policy_id": "pending_review",
  "dataset_version": "illustrative-only"
}
```

A practical SQLite model separates `entities`, `entity_aliases`, `provider_identifiers`, `field_observations`, `sources`, `license_policies`, `price_observations`, `route_estimates`, `accommodation_estimates`, `weather_observations` and `dataset_versions`. Keep raw provider payloads only if the applicable policy permits them. A runtime result envelope should include `status`, `source_mode`, `retrieved_at`, `valid_until`, `dataset_version`, `warnings` and `evidence_refs`. Suggested source modes are `curated_verified`, `curated_estimate`, `external_observation`, `heuristic` and `unknown`; “verified” means checked against a named source at a time, not guaranteed forever.

Unknown admission is not free admission, an empty route result is not zero travel time, and an API outage is not evidence that a venue is closed. The budget service must reject missing cost bases or carry a visible range/reserve. The review service should distinguish hard failures from evidence gaps, and the final itinerary should never claim validation passed when unresolved gaps invalidate feasibility.

### Freshness is an application decision constrained by provider rights

The following intervals are **proposed starting policies**, not provider guarantees or permissions to retain content. A provider's narrower storage rules always govern its data; zero persistent storage can be the correct setting. Refresh only when needed for active planning and permitted by source terms.

| Data class | Proposed local review or refresh policy | Decision when stale or unavailable |
| --- | --- | --- |
| Names, categories, coordinates | Monthly editorial review; earlier after reported changes | Flag questionable match or use vetted local record |
| Operator hours and closure notices | Recheck shortlisted venues before planning when access permits; recheck special schedules | Mark uncertain or exclude time-critical activity |
| Curated ticket/menu prices | Weekly editorial review and date-specific check where feasible | Show dated range and reserve; never guarantee payable total |
| RTA fares and fare rules | Review before releasing a dataset and after announced changes | Expose tariff version and fare assumptions |
| Route observations | Per run and applicable departure time; policy-bounded reuse | Use estimated interval and buffer or report insufficiency |
| Accommodation ranges | Review before dataset release and when price/season assumptions change | Display dated ranges and unknown fee inclusions; never claim availability |
| Weather | Refresh about every 1–3 hours for relevant near-term dates | Mark weather unavailable; avoid stale forecast claims |
| Crowd heuristics | Review on event/schedule changes and regular editorial cycle | Present uncertain guidance, never measured crowd count |
| GTFS, if approved | Validate every import and service-date expiry | Reject expired service coverage |

Keep licence domains separate in storage, logs, checkpoints, embeddings, exports and UI rendering. Attribution must travel with displayable values. Cache keys must include relevant language, source/version, transport mode, departure time, party/date parameters and price product, not just a place name. Strip credentials and personal data from traces. Treat all retrieved content as untrusted evidence; it cannot issue instructions to agents or invoke tools.

## 5. Prove access and coverage before expanding the integration surface

### Use staged delivery with explicit exit evidence

| Priority | Work package | Concrete output and acceptance evidence |
| --- | --- | --- |
| P0 | Curate local catalog and source registry | Reviewed, independently authored records; factual references; licence status; unknowns represented explicitly |
| P0 | Implement import validation and shared tools | JSON/CSV import into SQLite; required units/provenance; duplicate review; consistent results across LangGraph nodes |
| P0 | Establish estimates and deterministic fixtures | Cost ranges, route intervals and crowd heuristics labelled; synthetic fixtures visibly separate from real records |
| P0 | Demonstrate graceful degradation | Missing keys, timeout and empty results return local evidence or explicit insufficiency; unknown prices never become zero |
| P1 | Pilot one place discovery option | Sample 20 known Dubai locations across neighborhoods; measure matches, coordinates, category precision, hours completeness, attribution and cost |
| P1 | Pilot selected route legs | Verify modes, date-sensitive journeys, per-element failures, transit handling, fare gaps and request budgets |
| P1 | Add optional weather | Verify forecast-window boundary, timezone, attribution, hosted-use eligibility and outage behavior |
| P1 | Validate curated accommodation estimates | Document date, occupancy, nights, room basis, tax assumptions, and uncertainty |
| P2 | Validate official government/GTFS resource | Actual artifact, licence, no-charge access, schema, dates, refresh cadence and permitted use confirmed |
| P2 | Validate no-charge source eligibility | Confirm permitted use, hard quota limits, and absence of billable fallback paths |
| P2 | Automate approved editorial imports | Domain allowlist, rate controls, extraction validation, conflict review and rollback to last reviewed dataset |

Provider-specific acceptance tests should record both successes and absent fields. A 20-place pilot is a proposed evaluation size, not an existing measurement. Include less prominent neighborhoods, multiple venue types, Arabic/English aliases, duplicate branches and closures so the test does not only demonstrate famous landmarks. For route testing, include each enabled mode and verify actual supported Dubai coverage rather than extrapolating from the provider's general feature list.

### Control free-service quotas centrally and evaluate repeatably

Use shared rate limiters, bounded retries with backoff/jitter, request deadlines, and circuit breakers. Retry transient failures only. Respect applicable provider policies and Retry-After values. On quota exhaustion, show the local fallback and its freshness. Parallel graph nodes share one limiter so they cannot independently consume the same remaining allowance.

Set travel-data API spend to zero by source eligibility and request admission, not by assuming an account will never exceed a free tier. Do not configure paid credentials, subscription endpoints, or automatic upgrades. If a service cannot guarantee a no-charge usage path for this project, omit it. Free services still consume compute and network resources; measure calls, latency, failures, and fallback frequency. Model inference, local hardware, storage, and hosting have separate resource budgets.

For reproducible LangGraph evaluation, use a fixed permitted dataset version, request, model configuration, and tool-result scenario. Record run IDs and evidence references. Use independently authored or licensed fixtures. Evaluate optional live sources separately because changing source information prevents exact reproduction. Include quota exhaustion, missing data, expiry, and interrupted imports in the test suite.

### Outstanding verification work

Remaining checks are reusable no-charge government data, a current licensed GTFS artifact, eligible routing-service quotas and Dubai mode coverage, permitted map imports, and free weather-service eligibility. Restaurant dietary/accessibility completeness, special hours, price inclusions, and entrance quality need targeted editorial review. Treat all of these as planned capabilities until their coverage and failure tests pass. The local catalog must remain sufficient to demonstrate all five agents without external travel-data calls.

## Source bibliography

These primary sources support the retained findings; links do not imply that an integration or entitlement has been tested.

| Source family | References |
| --- | --- |
| OSM and geocoding | [Overpass resources](https://dev.overpass-api.de/overpass-doc/en/preface/commons.html); [ODbL FAQ](https://osmfoundation.org/wiki/Licence_and_Legal_FAQ); [attribution](https://osmfoundation.org/wiki/Attribution_Guidelines); [opening hours](https://wiki.openstreetmap.org/wiki/Opening_hours); [Nominatim policy](https://operations.osmfoundation.org/policies/nominatim/) |
| Tourism and government | [Visit Dubai terms](https://www.visitdubai.com/en/terms-of-use); [Dubai Pulse access example](https://gslb.dubaipulse.gov.ae/data/dld-registration/dld_projects-open?page=8); [UAE tourism-data directory](https://u.ae/en/information-and-services/visiting-and-exploring-the-uae/open-government-data-tourism-in-the-uae) |
| Public transport | [RTA fares](https://rta.ae/wps/portal/rta/ae/public-transport/Nol-Fares); [RTA open data](https://rta.ae/wps/portal/rta/ae/home/open-data?lang=en); [candidate GTFS—unverified](https://www.dubaipulse.gov.ae/data/rta-public-transports/rta_gtfs-open) |
| Routing | [OSRM API](https://project-osrm.org/docs/v5.9.1/api/); [openrouteservice](https://openrouteservice.org/dev/); [backend inputs](https://giscience.github.io/openrouteservice/run-instance/data) |
| Weather | [Open-Meteo forecast](https://open-meteo.com/en/docs); [free-service eligibility and limits](https://open-meteo.com/en/pricing); [licensing](https://github.com/open-meteo/open-meteo) |

## Conclusion

The key engineering boundary is the distinction between a reusable local fact and a context-dependent provider observation. Encoding that distinction in schemas, tool envelopes and review rules makes the LangGraph workflow easier to evaluate and prevents convincing language from hiding weak evidence. Any optional integration must improve itinerary feasibility or budget accuracy while retaining the no-charge acquisition requirement, explicit usage rights, and a reliable local fallback.
