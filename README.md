# Dubai AI Travel Planner

Phases 0-7 provide typed domain contracts, a policy-gated local catalog,
deterministic planning, model-driven specialists, a session-isolated LangGraph UI,
and a reproducible release matrix. No travel-data API credentials are required.
Groq runs orchestration, destination research, logistics, planning, scheduling and
budget; Gemini performs review when model mode is enabled. Fixture mode remains available for offline graph
verification and is never presented as model-generated reasoning.

## Local planner and data storage

Use the sidebar to open **Manage travel data**, **Plan a trip**, or **Saved itineraries**.
The data manager edits individual JSON records or imports a complete catalog. Saves
validate references and source permissions, create a new version, and preserve
source review dates. A review checkbox is an editorial acknowledgement, not
automatic fact verification. Add reviewed evidence before records that reference it.

The trip form accepts dates, travelers, accommodation, places and budget. Estimates
require explicit opt-in; missing or expired evidence remains visible. Generate an
itinerary, name it, then select **Save itinerary**. Reopen saved snapshots and use
**Recheck with current data** to recalculate without overwriting the original.
Catalogs and compressed plan snapshots share the configured local SQLite database
(normally `runtime/catalog.sqlite`). Repeated saves of the same result are deduplicated.
Storage grows with distinct versions and plans; no large datasets are downloaded.
JSON downloads are available subject to source permissions.

With this workspace's existing environment, launch without installing packages:

```powershell
.\runtime\verify-env\Scripts\python.exe -B -m streamlit run app.py --server.address 127.0.0.1 --server.headless true --browser.gatherUsageStats false
```

Open **Agent planner** for natural-language constraint extraction, structured
confirmation, background LangGraph execution, a safe event timeline, cancellation,
revision details, policy-aware downloads and explicit saving. Streamlit reruns retain
the active immutable request and do not duplicate work. Late results belong only to
their originating run and cannot replace a newer active run.

The Streamlit application explicitly reads a local `.env` when present. The CLI
continues to require `--env-file .env`; it never executes shell content.

## Streamlit Community Cloud deployment

The same repository supports two safe model configurations:

- **Local/private:** retain `.env` with `MODEL_ROUTING=parallel-ensemble` to use
  Groq plus local Ollama for planning and Gemini plus local Ollama for review.
- **Streamlit Community Cloud:** use `MODEL_ROUTING=groq-gemini`. Community Cloud
  cannot reach an Ollama server running on a personal computer.

For Community Cloud, push this repository to GitHub and deploy `app.py`. The
included `requirements.txt` installs the application dependencies. In the app's
**Secrets** settings, paste a copy of `.streamlit/secrets.toml.example` and replace
only the two placeholder API keys. The app reads these values through Streamlit's
secret store; they take precedence over a local `.env` and are never displayed.
Do not commit `.streamlit/secrets.toml` or `.env`.

On a fresh cloud start, the app securely initializes its SQLite catalog from the
reviewed seed included in this repository. Community Cloud filesystem storage is
temporary, so saved itineraries and catalog edits may be lost after a cloud restart;
use the JSON download to keep a copy or deploy to a host with persistent storage if
you need permanent saved trips.

## Model-driven LangGraph

```powershell
uv run dubai-data model-plan evaluation/phase2-request.json --env-file .env --base area-dubai-marina --accommodation rove-marina-quote-flex
uv run python scripts/verify_phase5.py --env-file .env --historical-evidence
```

These commands send the approved request and necessary catalog fields to Groq and
Gemini and may consume provider quota. The first six specialist roles use
`GROQ_MODEL`; review uses `GEMINI_MODEL`. Structured responses receive one bounded
schema repair, and every retry counts against the same call/token ledger. Python
services remain authoritative for scheduling, arithmetic and deterministic findings.

## Phase 4 fixture graph

```powershell
.\runtime\verify-env\Scripts\python.exe -B -m dubai_planner.cli fixture-plan evaluation/phase2-request.json --base area-dubai-marina --accommodation rove-marina-quote-flex
.\runtime\verify-env\Scripts\python.exe -B scripts/verify_phase4.py
```

The first command uses the active catalog and current clock; expired evidence
returns a partial result. The second reproduces historical success, a real cheaper
hotel repair, and expired-quote rejection without writing a database. It uses the
15 November evidence snapshot, not live availability.

Destination and preliminary-logistics fixture specialists run in parallel. An
explicit join feeds dedicated Planner and Scheduler nodes before deterministic
costing and review.
Repairs rebuild the schedule, costs and review, with at most two revisions.
Unchanged plans, missing evidence, deadlines and execution limits stop the run.
Events use static summaries, revision-specific artifact references and retry
deduplication. State stays in memory; no checkpoint database is created.

The deterministic planner remains available separately. Fixture runs demonstrate
graph mechanics, not model-generated reasoning.

## Phase 7 release evaluation

```powershell
uv run python scripts/verify_phase7.py --output evaluation/phase7-verification.json
uv run python scripts/verify_phase7.py --live --env-file .env --repetitions 5
```

The first command is the offline release baseline: it covers normal, one/seven-day,
party composition, missing input, low budget, stale evidence, accessibility gaps,
repair, no-progress, cancellation and local fallback paths. The second is explicitly
opt-in live model evaluation. Reports contain safe metrics and version identifiers,
not prompts, credentials or raw provider responses.

## Setup

Use Python 3.12 and `uv`. From the repository root:

```powershell
uv sync --locked
uv run dubai-data import
uv run dubai-data inspect
uv run streamlit run app.py
```

This workspace also contains `.tools/uv/uv.exe`; it can replace `uv` in these
commands. Dependency installation needs internet access. Catalog import, planning,
and tests work without travel-data network calls. `.env.example` documents optional
environment settings. The Streamlit app loads a local `.env` explicitly; CLI
commands load it only when given `--env-file .env`.

## Run deterministic planning

```powershell
uv run dubai-data plan evaluation/sample-request.json
uv run dubai-data export runtime/catalog-export.json
uv run dubai-data export runtime/catalog-export.csv
```

The example returns a typed four-day plan, AED cost information and stable rule
findings. It is **partial**, because critical prices, operating windows and routes
are not fully verified. It never replaces unknown costs with zero. To evaluate a
different accommodation area, pass `--base area-deira`; pass `--accommodation
stay-deira` to select an explicit option. Every call rebuilds routes, costs and
findings, including when comparing cheaper accommodation alternatives.

CLI input is structured JSON; the local UI offers deterministic and agent forms plus
natural-language extraction. The request distinguishes trip days,
hotel nights, traveler age bands and total-trip versus per-person budgets.

Phase 2's completed, dated example is separate from that deliberately incomplete
undated sample:

```powershell
uv run dubai-data plan evaluation/phase2-request.json --base area-dubai-marina --accommodation rove-marina-quote-flex
uv run python scripts/verify_phase2.py
```

See [the evidence, assumptions and reproduction guide](docs/phase2-example.md).
At the reviewed snapshot it returns `validated_estimate`, AED 2,940.30–4,153.60
including contingency, with a genuine cheaper hotel alternative. Planning
allowances require explicit opt-in; expired quotes correctly return `partial`.

## Checks

```powershell
uv run pytest -q
uv run ruff check src tests app.py scripts
uv run ruff format --check src tests app.py scripts
```

In restricted Windows environments, run pytest with a fresh workspace-local
temporary path (create `runtime` first), e.g. `--basetemp runtime/test-run-001`. Use a new directory name
for each run; pytest owns and may clean that directory. Tests use synthetic prices
and temporary SQLite files, never live travel services. The AED 1,260 architecture
fixture verifies room, ticket and shared taxi quantities.

## Data and import format

See [catalog and source review](docs/data-catalog.md). The versioned seed includes
27 places (14 attractions, 7 restaurants, 6 areas), 11 accommodation options,
60 price records, 54 route records (20 road-network estimates) and 4 tariff records. Unknown price
records count as records, not verified quotes. Rebuild with
`uv run python scripts/build_seed.py`; source facts require editorial review before
changing them or publishing a new dataset version.

Run `uv run dubai-data coverage` to inspect field-level gaps directly from the
seed without importing or accessing a network. The reviewed snapshot is in
`evaluation/data-coverage.json`. After rebuilding, run `uv run dubai-data import`
to activate the new version in the local catalog browser.

Latest selected-source review: **15 November 2026**, dataset `2026-11-15.2`.
The compact update adds two exact hotel snapshots, OSRM route evidence,
opt-in dated hours and spending allowances alongside verified entry and room facts. No new dependencies
or downloaded datasets are required. In the catalog screen, select a price date
and expand **Accommodation evidence** to inspect published offers and sources.
Run `uv run dubai-data coverage --on-date 2026-11-20` for a dated inventory.
The verified Rove promotion remains a starting price, not a complete hotel quote;
the original four-day example still correctly returns `partial`.

JSON imports use the `Catalog` schema. CSV imports use `kind,payload` columns:
one `metadata` row containing schema/dataset versions followed by rows for
`evidence`, `places`, `accommodation`, `prices`, `routes` and `tariffs`, each with a
JSON object payload. Exporting a catalog to CSV provides a template.

Imports validate schemas, unique IDs, references and independently configured
source policies before activating a version. The same version/content is
idempotent; different content needs a new version. Rejected imports retain the
previous active catalog and write a diagnostic report under `runtime/import-reports`.
Policies are checked again on reads and exports. Raw scraped pages are not stored.

## Current limits

- Straight-line heuristic routes do not establish connectivity and cannot pass
  route validation. The 20 OSRM-supported routes remain estimates between snapped
  approximate points, not exact entrance/accessibility or live-traffic guarantees.
- Prose opening hours do not establish date-specific windows. Structured reviewed
  windows are required for schedule validation; undated schedules remain qualified.
- Accommodation starting rates have no upper bound. Occupancy, fees, other meals
  and applicable dates must be confirmed before a complete budget is possible.
- Arbitrary hard constraints require supported evaluators; unresolved constraints
  remain errors. A failing selected plan is partial, not proof that every option
  is infeasible.
- Local mode contains no external adapters. Optional no-charge sources remain
  disabled pending access, quota, coverage and reuse review.

See [architecture](docs/architecture.md) and the
[Phase 0-7 implementation plan](docs/implementation%20Plan.md).
