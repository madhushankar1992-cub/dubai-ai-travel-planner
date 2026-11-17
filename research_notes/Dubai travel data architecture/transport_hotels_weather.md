# Transport, hotels, weather and crowd data acquisition

## Which transport sources are practical?

### Takeaway
Use curated, explicitly estimated journey costs and times for the reproducible MVP; optionally use Google Routes for date-sensitive journeys. Treat direct Dubai GTFS ingestion as a feasibility investigation until the official artifact, licence and service dates are verified.

### Cited Findings
- Google Routes supports both detailed transit routes and transit matrices. Transit `computeRoutes` does not accept intermediate waypoints; it provides stop, line and timing details. Transit fares appear only when fare information is available for every step. Traffic-routing options available for driving must not be applied indiscriminately to transit. [Google transit routing](https://developers.google.com/maps/documentation/routes/transit-route)
- `POST https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix` returns origin/destination-indexed distance/duration results, with per-element errors. Transit matrices are limited to 100 elements; ordinary non-transit matrices to 625, with 100 for `TRAFFIC_AWARE_OPTIMAL`. A response field mask is required. [Matrix documentation](https://developers.google.com/maps/documentation/routes/compute_route_matrix)
- Google requires billing and an API key or OAuth token. Compute Routes is charged per request; matrix usage per origin-destination element. SKU depends on requested capabilities. Set quotas; do not presume old universal monthly credits or hard-code an unverified price. [Usage and billing](https://developers.google.com/maps/documentation/routes/usage-and-billing)
- Google Routes has provider-specific attribution, display and content-use policies; it is not an unrestricted source for a permanent redistributable local dataset. [Routes policies](https://developers.google.com/maps/documentation/routes/policies)
- RTA's fare page defines zone-based pricing and intermodal transfers within 30 minutes; its table gives a maximum of three transfers and 180-minute journey duration. Card class, zones, transfer conditions and mode matter. [RTA nol fares](https://rta.ae/wps/portal/rta/ae/public-transport/Nol-Fares)
- RTA explicitly directs users to its Dubai Pulse contributions through its open-data page. This verifies an official discovery route, not a guaranteed runtime API or unrestricted reuse right for every dataset. [RTA open data](https://rta.ae/wps/portal/rta/ae/home/open-data?lang=en)
- OSRM exposes route/table services and profiles prepared from input data; supplied modes include car, bicycle and foot. Profiles are selected during graph preparation, so changing the URL profile string cannot create a missing routing graph. [OSRM API documentation](https://project-osrm.org/docs/v5.9.1/api/)
- ORS exposes directions APIs and API-key authentication. Its backend now documents a public-transport profile requiring a GTFS file. Therefore the statement “ORS cannot support public transport” is too broad; backend support does not establish hosted Dubai transit coverage. [ORS API](https://openrouteservice.org/dev/), [ORS backend data inputs](https://giscience.github.io/openrouteservice/run-instance/data)

### Inferences
- Recommended adapter flow: rank nearby candidates using a matrix, then fetch detailed adjacent selected legs at their actual departure times. Recompute subsequent legs after schedule changes. Never infer fare from road distance alone.
- Use `POST https://routes.googleapis.com/directions/v2:computeRoutes` with a narrow response mask for selected legs; confirm request shape against provider reference during implementation. Keep Google data ephemeral according to its terms; preserve provenance and attribution in UI.
- Prefer road-route alternatives only for supported modes. An OSRM road estimate is not a bus or metro itinerary. Open-source deployment shifts costs to hosting, graph building and data refresh; it does not eliminate operating costs or underlying data licences.
- Fallback: curated origin-area/destination-area duration intervals with mode labels, buffers and a source review date. If no credible estimate exists, report insufficient routing evidence rather than treating straight-line distance as a verified journey.
- A GTFS importer should validate feed licence, download authentication, integrity, `calendar`/`calendar_dates` coverage, agency time zone and service dates, and reject stale feeds. Static schedules do not imply live disruptions or vehicle positions.

### Gaps
- Candidate official resource: https://www.dubaipulse.gov.ae/data/rta-public-transports/rta_gtfs-open . The official page timed out twice during research. A third-party catalogue led to it, but the official data, licence, current service range and access requirements were not verified. Do not claim either “no Dubai GTFS exists” or “a current free GTFS feed is ready to integrate.”
- No current official Dubai GTFS-Realtime endpoint was verified. Live transit status therefore remains unproven.
- ORS main website was temporarily unavailable during research, and former plans URL returned 404. Hosted quota/cost/terms should be verified through its current dashboard before enabling it. Do not use archived staging plan numbers as current pricing.
- Exact RTA fare values should be reviewed from current official tables when seeding fixtures, including card purchase/usable balance distinction; this research did not establish a complete machine-readable tariff.

## How should accommodation data be obtained?

### Takeaway
Curated area and room-price ranges are adequate for the project's planning-only scope. Optional Amadeus production offers improve date-specific evidence, but sandbox data must never masquerade as current Dubai availability.

### Cited Findings
- Amadeus Hotel List discovers hotels by city, geocode or hotel IDs, returning identity and location. Endpoints include `/v1/reference-data/locations/hotels/by-city` and `/v1/reference-data/locations/hotels/by-geocode`. Hotel Search uses `/v3/shopping/hotel-offers` with hotel IDs and occupancy/date inputs. Prices and availability can change; the tutorial states that multiple-room totals require multiplying its per-room price by `roomQuantity`. [Official hotel tutorial](https://amadeus4dev.github.io/developer-guides/resources/hotels/)
- Authentication uses OAuth client credentials with a private API key/secret and token endpoint `/v1/security/oauth2/token`; use server-side storage and requests. [Amadeus authorization](https://amadeus4dev.github.io/developer-guides/API-Keys/authorization/)
- Test uses limited, cached data at `test.api.amadeus.com`; production uses live data at `api.amadeus.com`. The Hotel Search test collection has restricted hotel chains and recommends major cities such as London or New York. The documented general rate limits are 10 TPS test and 40 TPS production. [Test-data documentation](https://amadeus4dev.github.io/developer-guides/test-data/)
- Production retains a monthly free request quota, with additional calls charged; API-specific prices must be checked before activation. [Amadeus pricing](https://amadeus4dev.github.io/developer-guides/pricing/)
- Booking.com Demand API requires Managed Affiliate Partner registration, a contract/Partner Centre access, an API token and affiliate ID. It is a future partner integration rather than an anonymous free feed. [Access prerequisites](https://developers.booking.com/demand/docs/getting-started/prerequisites)
- Booking.com supports content-only and search/look/redirect integration patterns; booking inside this application is unnecessary for those patterns. [Integration choices](https://developers.booking.com/demand)

### Inferences
- Seed manually curated accommodation areas and representative nightly price ranges with source URLs, review dates, season/date context, room occupancy, meal assumptions, and explicit tax/fee inclusion fields. Clearly identify illustrative fixtures as such.
- Keep Hotel List metadata separate from a Hotel Offer. Metadata is not price or availability evidence. Preserve check-in/out, adults, children, rooms, currency, price basis, inclusions and observation timestamp in each quote.
- Budget by nights, not itinerary days. Normalize full-stay/per-night/per-room/per-person values before arithmetic and avoid counting taxes twice. If fee inclusion is unknown, expose the gap and use an explicit reserve assumption rather than asserting a final payable amount.
- Query offers only after candidate selection to control costs. Empty or failed results trigger curated estimates, not a claim that Dubai has no vacancies. Distinguish `sandbox`, `production_observation`, and `curated_estimate` in outputs.
- Affiliate/deep links and direct hotel pages are alternate reference routes; automated extraction needs permitted access and source-specific terms. No booking or payment tools are needed.

### Gaps
- Dubai coverage for chosen dates/hotels cannot be guaranteed without a credentialed production test. Current unit prices, contracted caching/redistribution rights and partner eligibility need account-specific confirmation.

## What can weather and crowd signals actually support?

### Takeaway
Use weather forecasts only within the provider's available date window. Treat crowd avoidance as an explained heuristic unless an authorized, independently validated crowd-data service is added.

### Cited Findings
- Open-Meteo's forecast endpoint provides seven days by default and up to sixteen days. It supports apparent temperature, precipitation probability, wind and other useful scheduling variables. [Forecast API](https://open-meteo.com/en/docs)
- Free hosted use is non-commercial with published limits of 600 calls/minute, 5,000/hour and 10,000/day, and no uptime guarantee. Paid plans use a commercial licence and `customer-api.open-meteo.com` with an API key. Pricing is monthly capacity-based; large variable/time requests may count as multiple calls. [Pricing/access](https://open-meteo.com/en/pricing)
- Open-Meteo data is CC BY 4.0 and requires attribution; server source is AGPLv3. Data licence and permission to use the hosted free service are separate considerations. [Official repository/licensing](https://github.com/open-meteo/open-meteo)
- Google Maps' consumer busyness feature uses aggregated opt-in location data and is only displayed when sufficient information exists; it is relative busyness, not an exact crowd count. [Google Maps help](https://support.google.com/maps/answer/11323117?hl=en)
- The documented Places resource does not expose a general popular-times/live-crowd field. Consumer Maps features should not be assumed to be available through Places API. [Places schema](https://developers.google.com/maps/documentation/places/web-service/reference/rest/v1/places)

### Inferences
- Example forecast request shape: `GET https://api.open-meteo.com/v1/forecast?latitude=25.2048&longitude=55.2708&hourly=apparent_temperature,precipitation_probability&timezone=Asia%2FDubai&forecast_days=16`. Fetch only relevant dates/variables and retain retrieval time/model metadata where available.
- For trips beyond the forecast window, use explicitly labelled seasonal guidance or omit weather-based optimization. Historical averages are not a forecast for a particular future day. For trips partly inside the window, mark the boundary per day.
- Suggested application freshness policy, not a provider SLA: refresh forecast observations every 1–3 hours when needed; preserve historical reference data separately. On outage, report unavailable weather and avoid carrying stale forecasts forward as current.
- Crowd records can contain a heuristic level, explanation, confidence, source and review date, derived from official event times or venue guidance and conservative time-of-day assumptions. Unknown must remain unknown. Rating/review counts and popularity are not live crowd measurements.
- Avoid undocumented scraping of consumer popular-times pages as a required integration. A future crowd vendor should pass Dubai venue-coverage, recency, measurement-method and contract checks before claims of real-time crowd avoidance are made.

### Gaps
- No verified authorized Dubai-wide live crowd feed was established. This project should promise preference-aware suggestions with uncertainty, not crowd-free locations or guaranteed waiting times.
