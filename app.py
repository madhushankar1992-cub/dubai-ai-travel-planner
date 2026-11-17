"""Local travel-data manager and deterministic itinerary planner."""

import os
import sys
from pathlib import Path

import streamlit as st

# Streamlit Community Cloud installs requirements.txt but not this repository as a
# package, so make the bundled src/ layout importable without a local editable install.
_SRC = str(Path(__file__).resolve().parent / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from dubai_planner.config import load_settings  # noqa: E402
from dubai_planner.providers.gateway import ProviderGateway  # noqa: E402
from dubai_planner.providers.policy import PolicyRegistry  # noqa: E402
from dubai_planner.storage.repository import CatalogRepository  # noqa: E402
from dubai_planner.ui.agent_workspace import agent_planner  # noqa: E402
from dubai_planner.ui.workspace import data_manager, saved_plans, trip_planner  # noqa: E402


def show_prices(prices) -> None:
    """Render catalog price evidence without exposing internal JSON records."""
    if not prices.data:
        st.info("Price unavailable — confirm the cost before making plans or a booking.")
        return
    for price in prices.data:
        unit = price.unit.replace("_", " ")
        if price.status == "unknown":
            st.info(f"Price unavailable — {price.reason}")
            continue
        if price.basis == "starting_from":
            amount = f"From AED {price.low}"
        elif price.low == price.high:
            amount = f"AED {price.low}"
        else:
            amount = f"AED {price.low}–{price.high}"
        qualifier = "estimate" if price.status == "estimated" else "published price"
        st.write(f"**{amount}** per {unit} ({qualifier})")
        details = []
        if price.age_category:
            details.append(price.age_category)
        if price.taxes_fees != "included":
            details.append("taxes and fees need confirmation")
        if price.requires_opt_in:
            details.append("planning estimate requires opt-in")
        if details:
            st.caption(" · ".join(details))


st.set_page_config(page_title="Dubai Trip Studio", page_icon=":palm_tree:", layout="wide")
st.markdown(
    """
    <style>
    .block-container {max-width: 1180px; padding-top: 2.2rem;}
    [data-testid="stMetric"] {background: #f7f3eb; border-radius: 14px; padding: 14px;}
    [data-testid="stExpander"] {border-radius: 12px; border-color: #e4ddd1;}
    </style>
    """,
    unsafe_allow_html=True,
)
st.title("Dubai Trip Studio")
st.caption("Thoughtful Dubai itineraries, clear budgets, and practical day plans.")
try:
    env_file = Path(".env")
    # Community Cloud exposes deployment values through st.secrets; local work keeps
    # using .env. Values are passed only to the validated settings loader and never
    # displayed or logged.
    try:
        secret_values = {str(key).upper(): str(value) for key, value in st.secrets.items()}
    except FileNotFoundError:
        # Local installations do not need a .streamlit/secrets.toml file.
        secret_values = {}
    settings = load_settings(
        {**os.environ, **secret_values}, env_file=env_file if env_file.exists() else None
    )
    repository = CatalogRepository(
        settings.database_path, PolicyRegistry.load(Path("config/provider_policies/sources.json"))
    )
    try:
        catalog = repository.load()
    except FileNotFoundError:
        # A fresh Streamlit Cloud container has no runtime SQLite file. Bootstrap
        # only the reviewed catalog that is bundled with this repository.
        repository.import_file(settings.dataset_path, Path("runtime/import-reports"))
        catalog = repository.load()
except (ValueError, OSError) as exc:
    st.warning(str(exc))
    st.code("uv run dubai-data import")
    st.stop()

st.sidebar.title("Dubai Trip Studio")
st.sidebar.caption("Plan first. Review details when you need them.")
page = st.sidebar.radio(
    "Navigate",
    [
        "Plan a trip",
        "Agent planner",
        "Saved itineraries",
        "Browse Dubai",
        "Manage travel data",
    ],
)
if page != "Browse Dubai":
    {
        "Manage travel data": data_manager,
        "Plan a trip": trip_planner,
        "Agent planner": lambda repo, data: agent_planner(repo, data, settings),
        "Saved itineraries": saved_plans,
    }[page](repository, catalog)
    st.stop()
st.header("Explore Dubai")
st.caption(
    "Save ideas for your trip. Prices and opening times are shown only when the local evidence supports them."
)
filters, price_filter = st.columns([3, 1])
with filters:
    query = st.text_input("Search places, food, neighbourhoods, or attractions")
    category = st.selectbox("Show", ["All", "attraction", "restaurant", "area"])
with price_filter:
    price_date = st.date_input("Travel date", value=None)
gateway = ProviderGateway(repository)
result = gateway.search_places(query, category=None if category == "All" else category, limit=100)
for warning in result.warnings:
    st.warning(warning)
for place in result.data or []:
    with st.expander(f"{place.name} | {place.area}"):
        st.write(place.summary)
        st.write(
            f"Suggested visit: {place.visit_minutes_min}-{place.visit_minutes_max} minutes (editorial estimate)"
        )
        st.write(f"Hours: {place.hours or 'Unknown - confirm before scheduling'}")
        st.write(f"Accessibility: {place.accessibility}")
        prices = gateway.get_price(place.id, on_date=price_date)
        for warning in prices.warnings:
            st.caption(warning)
        show_prices(prices)
        refs = {e for values in place.field_evidence.values() for e in values}
        refs.update(e.id for e in prices.evidence)
        sources = {e.id: e for e in [*result.evidence, *prices.evidence]}
        for evidence in sources.values():
            if evidence.id in refs:
                st.write(
                    f"{evidence.attribution} - {evidence.quality} - reviewed {evidence.retrieved_at.date()}"
                )
                if evidence.url:
                    st.link_button("Source reference", evidence.url)

st.subheader("Where to stay")
st.caption(
    "Accommodation guidance and published price evidence. Availability is always confirmed directly with the property."
)
for stay in gateway.search_accommodation().data or []:
    with st.expander(stay.name):
        st.write(stay.notes)
        st.write(f"Maximum room occupancy: {stay.max_occupancy or 'Unconfirmed'}")
        prices = gateway.get_price(stay.id, on_date=price_date)
        for warning in prices.warnings:
            st.caption(warning)
        show_prices(prices)
        evidence_by_id = {e.id: e for e in catalog.evidence}
        for ref in sorted(set(stay.evidence_ids) | {e.id for e in prices.evidence}):
            evidence = evidence_by_id[ref]
            if evidence.url:
                st.link_button(f"Source: {evidence.attribution}", evidence.url)
