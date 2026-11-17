# Phase 2 reviewed four-day example

Dataset `2026-11-15.2` supports an offline, four-day **validated estimate** for
20–23 November 2026: one adult, one room, three nights, AED 5,000 cap. It starts
and ends at the Dubai Marina area base. It is a demonstration, not a reservation
or the user's travel dates. Flights, airport transfers, visas, shopping and
personal incidentals are outside this example.

The scheduled visits are Al Seef, Dubai Frame, Al Shindagha Museum and Dubai Mall,
one per day. The small selection is deliberately paced across all four days.
Three meals per day are costed; the room-only hotel supplies no breakfast credit.

## Evidence and assumptions

- Fostay's public read-only `get_live_rates` tool returned Rove Dubai Marina,
  Rover Room Marina View, 20–23 November, one adult/no children, AED 1,557 refundable
  or AED 1,535 non-refundable, whole-stay totals including all taxes/fees and
  AED 0 collected at check-in. The refundable deadline is 18 November at 14:00
  Dubai time, followed by an AED 1,557 cancellation charge. These are two genuine
  room-only alternatives. No booking or offer token is stored. The exact dates,
  guest count and room count must match; snapshots expire after one day.
- The OSRM driving matrix returned road connections between all five approximate
  catalog points. Raw distances/durations are retained as small numeric arrays
  in `scripts/phase2_evidence.py`. No maps are downloaded. These support estimated
  taxi journeys between snapped points; they do not prove exact entrance access,
  accessibility, dispatch availability, live traffic or future road conditions.
- Timing uses `ceil(seconds/60)+10` minutes as the lower allowance and twice that
  amount plus ten minutes as the upper allowance, including access/waiting/traffic.
  The scheduler does not add its travel contingency a second time.
- Published recurring opening hours are projected **only** onto the four demo
  dates. Every projected window is marked `estimated` and requires explicit
  acceptance. Closures and special dates must be rechecked. Shindagha hours come
  from the indexed official brochure; direct retrieval timed out.
- Meal spending is an original allowance of AED 30–80 per person per meal.
  Taxi spending per traveler per journey is `ceil(km*2.5+15)` to
  `ceil(km*4+35)` AED. This conservatively budgets a car allowance for each traveler
  without a sharing discount. These include provisional fee reserves, not quoted
  tariffs, market guarantees or guaranteed upper bounds.
- Paid adult ticket allowances range from the published base to
  `base*1.05+10` AED, allowing for provisional VAT/fees. Original published prices
  with unresolved fee status remain separate. Free browsing at Al Seef and Dubai
  Mall excludes purchases and separately ticketed experiences.

The request explicitly selects these allowances and sets
`accept_planning_estimates: true`. Ordinary requests default to false. Removing
acceptance, a required route, meal coverage or quote freshness prevents validation.
The result means the disclosed estimate fits the cap, not that suppliers guarantee
these prices or availability. A separate 10% budget contingency is included.

## Reproduce

```powershell
uv run python scripts/build_seed.py
uv run dubai-data import
uv run dubai-data plan evaluation/phase2-request.json --base area-dubai-marina --accommodation rove-marina-quote-flex
uv run python scripts/verify_phase2.py
```

`plan` uses the current time and correctly rejects stale evidence.
`verify_phase2.py` explicitly evaluates the historical snapshot as of
15 November 2026, 18:00 UTC and writes the compact `evaluation/phase2-result.json`.
It is a reproducibility check, never a live booking check. The non-refundable
alternative uses `rove-marina-quote-nonrefund`.

## Retention and attribution

Selected factual numbers and reference links only: no page bodies, hotel images,
booking credentials, map extracts or additional dependencies. All runtime planning
stays local. The source registry gates each field's read/persist/export operations.

Road data © OpenStreetMap contributors, via OSRM/FOSSGIS. OSM-derived numeric route
records are available under the [ODbL](https://opendatacommons.org/licenses/odbl/1-0/);
see [attribution](https://www.openstreetmap.org/copyright). These terms do not
relicense unrelated hotel or editorial records. Hotel research reference:
[Fostay agent interface](https://fostay.com/agents). Published opening and entry
sources are recorded individually in the catalog and source registry.

This completes the bounded Phase 2 example and local-data acceptance, not broad
Dubai coverage, production booking readiness, or Phases 4–7. Other catalog records
retain unknown prices, unsupported routes and accessibility gaps.
