"""Session-isolated LangGraph planning workspace for Streamlit."""

import sqlite3
from datetime import date, timedelta
from uuid import uuid4

import streamlit as st

from dubai_planner.agents.model_specialist import extract_request
from dubai_planner.domain.requests import TripRequest
from dubai_planner.services.run_service import (
    SessionRunRegistry,
    model_session,
    run_fixture,
    run_model,
)
from dubai_planner.storage.plans import PlanRepository
from dubai_planner.ui.workspace import show_plan

ROLE_TASKS = (
    ("Orchestrator", "parse"),
    ("Destination Research", "destination"),
    ("Logistics", "preliminary"),
    ("Planner", "planner"),
    ("Scheduler", "scheduler"),
    ("Budget", "costing"),
    ("Review", "review"),
)


def role_progress(events):
    """Return safe UI status from static event kinds; no prompts or reasoning."""
    rows = []
    for role, task in ROLE_TASKS:
        related = [event for event in events if event.task_id == task]
        completed = [event for event in related if event.kind == "artifact_ready"]
        started = [event for event in related if event.kind == "agent_started"]
        status = "complete" if completed else ("running" if started else "waiting")
        revision = max((event.revision for event in related), default=0)
        rows.append({"role": role, "status": status, "latest revision": revision})
    return rows


def _session_registry():
    key = "agent_run_registry"
    if key not in st.session_state:
        st.session_state[key] = SessionRunRegistry()
    return st.session_state[key]


def _request_form(catalog):
    stays = {stay.id: stay for stay in catalog.accommodation}
    places = {place.id: place for place in catalog.places if place.category != "area"}
    # These four have reviewed hours and routes in the curated dataset, so the scheduler
    # can place them. Places without that evidence are left for the user to opt into.
    default_places = [
        key for key in ("al-seef", "dubai-frame", "shindagha", "dubai-mall") if key in places
    ]
    default_date = max(date.today(), date(2026, 11, 20))
    with st.form("agent-structured-request"):
        st.subheader("Confirmed planning constraints")
        start = st.date_input("First trip day", value=default_date, key="agent-start")
        days = st.number_input("Trip days", 1, 7, 4, key="agent-days")
        nights = st.number_input("Hotel nights", 0, 30, 3, key="agent-nights")
        adults = st.number_input("Adults", 1, 20, 1, key="agent-adults")
        st.caption("Children by age band")
        child_counts = st.columns(4)
        children = {
            band: child_counts[index].number_input(band, 0, 10, 0, key="agent-children-" + band)
            for index, band in enumerate(("0-2", "3-5", "6-12", "13-17"))
        }
        rooms = st.number_input("Rooms", 1, 20, 1, key="agent-rooms")
        budget = st.text_input("Total trip budget (AED)", "5000", key="agent-budget")
        interests = st.multiselect(
            "Interests",
            ["culture", "food", "beach", "shopping", "architecture", "family"],
            default=["culture", "food", "beach"],
            key="agent-interests",
        )
        stay_id = st.selectbox(
            "Accommodation",
            list(stays),
            index=list(stays).index("rove-marina-quote-flex")
            if "rove-marina-quote-flex" in stays
            else 0,
            format_func=lambda key: stays[key].name,
            key="agent-stay",
        )
        candidates = st.multiselect(
            "Approved places to consider",
            list(places),
            default=default_places,
            format_func=lambda key: places[key].name,
            key="agent-candidates",
        )
        transport = st.multiselect(
            "Transport preferences",
            ["taxi", "walk", "transit", "abra"],
            default=["taxi"],
            key="agent-transport",
        )
        estimates = st.checkbox(
            "Accept the displayed planning allowances and recurring-hours projections",
            key="agent-estimates",
        )
        submitted = st.form_submit_button("Start agent planning")
    if not submitted:
        return None
    request = TripRequest(
        id="agent-trip-" + uuid4().hex,
        days=days,
        nights=nights,
        arrival=start,
        departure=start + timedelta(days=days - 1),
        check_in=start if nights else None,
        check_out=start + timedelta(days=nights) if nights else None,
        travelers={
            "adults": adults,
            "child_age_bands": [band for band, count in children.items() for _ in range(count)],
        },
        rooms=rooms,
        budget=budget,
        budget_scope="total_trip",
        interests=interests,
        candidate_ids=candidates,
        transport_preferences=transport,
        accept_planning_estimates=estimates,
        price_choices={
            price.entity_id: price.id
            for price in catalog.prices
            if estimates and price.id in {"allowance-dubai-frame", "allowance-shindagha"}
        },
        meal_allowance_price_id="price-meal-allowance"
        if estimates and any(price.id == "price-meal-allowance" for price in catalog.prices)
        else None,
        exclusions=["flights", "airport transfers", "visas", "personal incidentals"],
        assumptions=[
            "No booking or live availability is confirmed.",
            "Trip starts and ends at the selected accommodation area.",
        ]
        + (
            ["Accepted the displayed local planning allowances and projected hours."]
            if estimates
            else []
        ),
    )
    return request, stays[stay_id]


def _show_extraction(catalog, settings):
    with st.form("natural-language-request"):
        text = st.text_area(
            "Describe your Dubai trip",
            placeholder="Four days in Dubai for one adult, AED 5,000 total...",
        )
        extract = st.form_submit_button(
            "Extract constraints with Groq", disabled=not settings.capabilities["model_runner"]
        )
    if not settings.capabilities["model_runner"]:
        st.caption("Add both private API keys to enable natural-language extraction.")
    if extract:
        try:
            _, gateway = model_session(catalog, settings)
            proposed = extract_request(text, gateway)
            st.session_state["extracted_request"] = proposed.model_dump_json()
        except ValueError as exc:
            st.error(str(exc))
    if st.session_state.get("extracted_request"):
        from dubai_planner.agents.model_specialist import ExtractedRequest

        proposed = ExtractedRequest.model_validate_json(st.session_state["extracted_request"])
        st.write(proposed.summary)
        if proposed.clarification_fields:
            st.warning("Confirm before planning: " + ", ".join(proposed.clarification_fields))
        if proposed.request:
            st.caption("Extracted assumptions and constraints — review the structured form below.")
            st.json(proposed.request.model_dump(mode="json"), expanded=False)


def _show_run(snapshot, store, registry, catalog):
    st.subheader("Agent run")
    st.write(f"Status: **{snapshot.state.replace('_', ' ')}**")
    left, right = st.columns(2)
    if left.button(
        "Cancel run",
        disabled=snapshot.state not in {"queued", "running", "cancel_requested"},
        key="cancel-agent-run",
    ):
        registry.cancel(snapshot.run_id)
        st.rerun()
    if right.button("Refresh progress", key="refresh-agent-run"):
        st.rerun()
    if snapshot.events:
        st.caption("Orchestrator → Destination + Logistics → Planner → Scheduler → Budget → Review")
        st.dataframe(role_progress(snapshot.events), hide_index=True)
        st.markdown("**Sanitized LangGraph timeline**")
        st.dataframe(
            [
                {
                    "#": event.sequence,
                    "time": event.timestamp.isoformat(),
                    "specialist/task": event.task_id or "run",
                    "revision": event.revision,
                    "event": event.summary,
                    "artifacts": ", ".join(event.artifact_ids),
                }
                for event in snapshot.events
            ],
            hide_index=True,
        )
    if snapshot.error:
        st.error(snapshot.error)
    if not snapshot.result:
        st.info("Planning continues in the session worker. Refresh to collect new safe events.")
        return
    result = snapshot.result
    provider_calls = {
        "Groq": result.metrics.get("calls_provider_groq", 0),
        "Gemini": result.metrics.get("calls_provider_gemini", 0),
    }
    if any(provider_calls.values()):
        st.markdown("**AI provider activity**")
        columns = st.columns(len(provider_calls))
        for column, (provider, calls) in zip(columns, provider_calls.items()):
            column.metric(provider, f"{calls} call{'s' if calls != 1 else ''}")
    else:
        st.info(
            "This completed run used the offline fixture workflow. It made no Groq or Gemini calls. "
            "Choose an AI agents execution mode for live model calls."
        )
    if result.agent_summaries:
        with st.expander("Specialist contributions"):
            for summary in result.agent_summaries:
                st.write(summary)
    show_plan(result, store, catalog=catalog)
    label = st.text_input("Save this agent itinerary as", "Agent-planned Dubai trip")
    if st.button("Save agent itinerary"):
        try:
            store.save(result, label)
            st.success("Saved explicitly under the active source policy.")
        except (ValueError, OSError, sqlite3.Error) as exc:
            st.error(str(exc))


def agent_planner(repository, catalog, settings):
    st.header("LangGraph agent planner")
    st.caption(
        "Groq runs the six planning agents; Gemini performs the review. "
        "Travel facts remain local and policy-gated."
    )
    review_label = "Gemini Review"
    model_label = "AI agents (Groq + Gemini)"
    st.info(
        "Workflow: Orchestrator → parallel Destination Research and Logistics → Planner → "
        f"Scheduler → Budget → {review_label}. Repairs return to Planner and rebuild every downstream artifact."
    )
    _show_extraction(catalog, settings)
    options = ["Fixture graph"]
    if settings.capabilities["model_runner"]:
        options.insert(0, model_label)
    mode_label = st.radio("Execution mode", options, horizontal=True)
    submitted = _request_form(catalog)
    registry = _session_registry()
    if submitted:
        try:
            request, stay = submitted
            clarifications = request.clarification_fields()
            if clarifications:
                st.warning("Confirm before planning: " + ", ".join(clarifications))
            else:
                mode = "model" if mode_label.startswith("AI") else "fixture"

                def execute(run_id, immutable_request, emit, cancelled):
                    common = dict(
                        settings=settings,
                        base_id=stay.area_id,
                        accommodation_id=stay.id,
                        emit_event=emit,
                        cancelled=cancelled,
                        run_id=run_id,
                    )
                    runner = run_model if mode == "model" else run_fixture
                    return runner(immutable_request, catalog, repository.registry, **common)

                registry.start(
                    request,
                    mode=mode,
                    configuration={
                        "dataset": catalog.dataset_version,
                        "base": stay.area_id,
                        "accommodation": stay.id,
                        "groq_model": settings.groq_model if mode == "model" else None,
                        "gemini_model": settings.gemini_model if mode == "model" else None,
                        "model_routing": settings.model_routing if mode == "model" else None,
                        "max_revisions": settings.max_revisions,
                    },
                    execute=execute,
                )
                st.rerun()
        except (ValueError, OSError) as exc:
            st.error(str(exc))
    snapshot = registry.snapshot()
    if snapshot:
        _show_run(
            snapshot, PlanRepository(repository.database, repository.registry), registry, catalog
        )
