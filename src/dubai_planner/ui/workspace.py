"""Local data management and deterministic planning; no model or network calls."""

import json
import sqlite3
from datetime import date, timedelta
from uuid import uuid4

import streamlit as st

from dubai_planner.domain.requests import TripRequest
from dubai_planner.domain.review import PlanResult
from dubai_planner.services.catalog_editor import COLLECTIONS, edited_catalog
from dubai_planner.services.planner import plan_local
from dubai_planner.storage.plans import PlanRepository
from dubai_planner.storage.repository import ImportRejected


def data_manager(repository, catalog):
    st.header("Manage travel data")
    st.write(
        "Add or edit source-backed facts. Unknown values stay unknown; estimates must be labelled. Every save creates a catalog version and preserves earlier versions."
    )
    collection = st.selectbox("Record type", COLLECTIONS)
    records = {r.id: r for r in getattr(catalog, collection)}
    selected = st.selectbox("Record", ["Add new record", *records])
    record = records.get(selected)
    example = record or next(iter(records.values()), None)
    initial = example.model_dump(mode="json") if example else {"id": "new-record"}
    if record is None:
        initial["id"] = "new-record"
    st.caption(
        "The new-record template copies an existing record's shape. Replace its facts and evidence before saving; it is not new verified data."
    )
    with st.form(f"edit-{catalog.dataset_version}-{collection}-{selected}"):
        content = st.text_area("Record JSON", json.dumps(initial, indent=2), height=330)
        reviewed = st.checkbox(
            "I checked these facts and their source permissions; estimates and unknowns are labelled."
        )
        save = st.form_submit_button("Validate and save record")
    if save:
        try:
            if not reviewed:
                raise ValueError("Review the facts and source permissions before saving")
            updated = edited_catalog(
                catalog, collection, content, original_id=record.id if record else None
            )
            updated.check_policy(repository.registry, "persist")
            repository.import_json(
                updated.model_dump_json(),
                repository.database.parent / "import-reports",
                expected_version=catalog.dataset_version,
            )
            st.session_state["catalog_saved"] = updated.dataset_version
            st.rerun()
        except (ValueError, OSError, sqlite3.Error, ImportRejected) as exc:
            st.error(str(exc))
    if st.session_state.get("catalog_saved"):
        st.success("Saved catalog version: " + st.session_state["catalog_saved"])
    with st.expander("Source registry and field permissions"):
        st.write(
            "Sources must be independently reviewed in config/provider_policies/sources.json. Editing a catalog cannot approve a new source. Add evidence first, then records that reference it. Editing a record does not refresh its source review date."
        )
        st.dataframe(
            [
                dict(
                    id=p.id,
                    owner=p.owner,
                    fields=", ".join(p.allowed_fields),
                    approved=p.approved,
                    persistence=p.persistence,
                )
                for p in repository.registry.policies.values()
            ],
            hide_index=True,
        )
    with st.expander("Import a complete catalog"):
        upload = st.file_uploader("Reviewed catalog JSON (maximum 10 MB)", type=["json"])
        confirmed = st.checkbox("I reviewed the uploaded catalog and its source evidence.")
        if st.button("Validate and import catalog", disabled=upload is None):
            try:
                if not confirmed:
                    raise ValueError("Review the catalog before importing")
                if upload.size > 10_000_000:
                    raise ValueError("Catalog exceeds 10 MB")
                report = repository.import_json(
                    upload.getvalue().decode("utf-8"),
                    repository.database.parent / "import-reports",
                    expected_version=catalog.dataset_version,
                )
                st.session_state["catalog_saved"] = report["dataset_version"]
                st.rerun()
            except (ValueError, OSError, sqlite3.Error, ImportRejected) as exc:
                st.error(str(exc))
    try:
        catalog.check_policy(repository.registry, "export")
    except ValueError as exc:
        st.warning(f"Export unavailable: {exc}")
        return
    st.download_button(
        "Download catalog JSON",
        catalog.model_dump_json(indent=2),
        "travel-catalog.json",
        "application/json",
    )


def _display_name(catalog, record_id):
    if catalog is None:
        return record_id.replace("-", " ").title()
    records = [*catalog.places, *catalog.accommodation]
    return next(
        (record.name for record in records if record.id == record_id),
        record_id.replace("-", " ").title(),
    )


def _display_window(window):
    if window.kind == "dated":
        start = window.start.strftime("%a %d %b, %I:%M %p").lstrip("0")
        end = window.end.strftime("%I:%M %p").lstrip("0")
        return f"{start} - {end}"
    return (
        f"Day {window.day}, {window.start_minute // 60:02d}:{window.start_minute % 60:02d}"
        f" - {window.end_minute // 60:02d}:{window.end_minute % 60:02d}"
    )


def show_plan(result, store, *, catalog=None, historical=False):
    _show_traveler_plan(result, store, catalog=catalog, historical=historical)
    return

    if historical:
        st.warning(
            "Saved snapshot: its status was calculated when generated. Recheck against the current catalog before relying on prices or availability."
        )
    status_messages = {
        "needs_input": ("warning", "More information is required before planning can continue."),
        "validated_estimate": (
            "success",
            "Evaluated hard constraints passed under the displayed evidence and assumptions; this is not a booking guarantee.",
        ),
        "partial": (
            "warning",
            "Your itinerary is ready to review. A few trip details still need confirmation before you rely on the final total.",
        ),
        "infeasible": (
            "error",
            "A conflict was demonstrated within the supplied constraints and available candidates.",
        ),
        "failed": ("error", "Planning stopped before a usable plan could be produced."),
        "cancelled": ("info", "This run was cancelled; late worker output is ignored."),
    }
    st.subheader("Your Dubai itinerary")
    kind, message = status_messages[result.status]
    getattr(st, kind)(message)
    overview, stay_column, budget_column = st.columns(3)
    overview.metric("Plan status", result.status.replace("_", " ").title())
    if result.accommodation:
        stay_column.metric("Stay", result.accommodation[0].name)
    if result.budget:
        budget = result.budget
        if budget.total_low is not None:
            budget_column.metric(
                "Trip estimate",
                f"AED {budget.total_low:,.2f} – {budget.total_high:,.2f}",
            )
        else:
            budget_column.metric("Known subtotal", f"AED {budget.known_subtotal:,.2f}")
            st.warning("The total is incomplete. Missing costs have not been treated as free.")
        st.write(f"Known subtotal: AED {budget.known_subtotal:,.2f}")
        if budget.estimated_low is not None:
            st.write(
                f"Estimated components: AED {budget.estimated_low:,.2f} – {budget.estimated_high:,.2f}"
            )
        if budget.contingency_low is not None and budget.contingency is not None:
            st.write(
                f"Contingency range: AED {budget.contingency_low:,.2f} – {budget.contingency:,.2f}"
            )
        st.write("Budget status: " + budget.compliance)
        if budget.exclusions:
            st.caption("Excluded: " + ", ".join(budget.exclusions))
        for gap in budget.missing_required_costs:
            st.caption(gap)
    for day in result.days:
        with st.expander(f"Day {day.day}", expanded=True):
            st.caption(day.base_assumption)
            for activity in day.activities:
                st.markdown(
                    f"**{_display_window(activity.window)} - {_display_name(catalog, activity.place_id)}**"
                )
                details = [f"for {activity.participants} traveler(s)"]
                if activity.booking_required:
                    details.append("booking may be required")
                if activity.hours_check != "checked":
                    details.append("opening hours need confirmation")
                st.caption(" | ".join(details))
            for break_slot in day.breaks:
                st.caption(f"{break_slot.kind.title()} break: {_display_window(break_slot.window)}")
            for leg in day.routes:
                st.caption(
                    f"{leg.origin_id} → {leg.destination_id}: {leg.mode}, {leg.duration_min}–{leg.duration_max} min ({leg.status})"
                )
            for note in day.meal_rest_notes:
                st.caption(note)
    if result.findings:
        st.dataframe(
            [dict(rule=f.rule_id, severity=f.severity, message=f.message) for f in result.findings],
            hide_index=True,
        )
    with st.expander("Assumptions, sources and freshness"):
        for assumption in result.assumptions:
            st.write(assumption)
        if result.freshness_warnings:
            st.warning("Evidence needing review: " + ", ".join(result.freshness_warnings))
        st.dataframe(
            [
                dict(
                    source=e.attribution,
                    url=e.url,
                    reviewed=str(e.retrieved_at),
                    quality=e.quality,
                    method=e.method,
                )
                for e in result.sources
            ],
            hide_index=True,
        )
    try:
        exported = store.export(result)
    except ValueError as exc:
        st.warning(f"Export unavailable: {exc}")
        return
    st.download_button(
        "Download itinerary JSON",
        exported,
        "itinerary.json",
        "application/json",
        key="download-" + result.run_id,
    )


def _show_traveler_plan(result, store, *, catalog, historical):
    """Present a trip result as traveler guidance, not an engineering report."""
    if historical:
        st.info(
            "This is a saved trip. Recheck it before travel because prices and hours can change."
        )

    st.subheader("Your Dubai itinerary")
    messages = {
        "validated_estimate": (
            "success",
            "Your plan fits the checks completed with the available trip information.",
        ),
        "partial": (
            "warning",
            "Your plan is ready to review. A few details need confirmation before you travel.",
        ),
        "needs_input": ("warning", "Add the missing trip details and we can finish your plan."),
        "infeasible": (
            "error",
            "This combination of preferences and budget is not workable with the available options.",
        ),
        "failed": ("error", "We could not finish this plan. Please try again."),
        "cancelled": ("info", "This plan was cancelled."),
    }
    kind, message = messages[result.status]
    getattr(st, kind)(message)

    status, stay, cost = st.columns(3)
    status.metric("Trip plan", "Ready" if result.status == "validated_estimate" else "Needs review")
    if result.accommodation:
        stay.metric("Where you stay", result.accommodation[0].name)
    if result.budget and result.budget.total_low is not None:
        cost.metric(
            "Estimated trip cost",
            f"AED {result.budget.total_low:,.0f} - {result.budget.total_high:,.0f}",
        )
    elif result.budget and result.budget.estimated_low is not None:
        cost.metric(
            "Current estimate",
            f"AED {result.budget.estimated_low:,.0f} - {result.budget.estimated_high:,.0f}",
        )
    else:
        cost.metric("Trip cost", "To confirm")

    if result.budget and result.budget.total_low is None:
        st.caption(
            "The displayed estimate does not include every cost yet. Confirm the items below before relying on it."
        )

    for day in result.days:
        with st.expander(f"Day {day.day}", expanded=True):
            for activity in day.activities:
                st.markdown(
                    f"**{_display_window(activity.window)} | {_display_name(catalog, activity.place_id)}**"
                )
                notes = []
                if activity.booking_required:
                    notes.append("booking may be needed")
                if activity.hours_check != "checked":
                    notes.append("confirm opening hours")
                if notes:
                    st.caption(" • ".join(notes))
            for break_slot in day.breaks:
                st.caption(f"{break_slot.kind.title()} break: {_display_window(break_slot.window)}")
            for leg in day.routes:
                duration = (
                    f"{leg.duration_min}-{leg.duration_max} min"
                    if leg.duration_min is not None
                    else "time to confirm"
                )
                st.caption(
                    f"{_display_name(catalog, leg.origin_id)} to {_display_name(catalog, leg.destination_id)} by {leg.mode}: {duration}"
                )

    guidance = {
        "OCCUPANCY_UNKNOWN": "Confirm the room is available for your group.",
        "EMPTY_DAY": "Add an activity for this day before you travel.",
        "REST_MISSING": "Plan a meal or rest break for this day.",
        "BUDGET_UNKNOWN": "Confirm remaining prices and fees to finish the total trip budget.",
    }
    pending = []
    if result.budget:
        pending.extend(result.budget.missing_required_costs)
    pending.extend(guidance.get(finding.rule_id, finding.message) for finding in result.findings)
    if pending:
        with st.expander("What to confirm before you go"):
            for item in dict.fromkeys(pending):
                st.write("- " + item)

    with st.expander("Trip notes and sources"):
        for assumption in result.assumptions:
            st.caption(assumption)
        for source in result.sources:
            if source.url:
                st.link_button(source.attribution, source.url)

    try:
        exported = store.export(result)
    except ValueError:
        return
    with st.expander("Export this itinerary"):
        st.caption("Optional: download a JSON copy to keep or reuse the plan data.")
        st.download_button(
            "Download itinerary data",
            exported,
            "itinerary.json",
            "application/json",
            key="download-" + result.run_id,
        )


def trip_planner(repository, catalog):
    st.header("Plan your Dubai trip")
    st.caption("Build a practical day-by-day plan from reviewed local travel information.")
    st.info(
        "Choose your dates, budget, hotel and interests. Your itinerary will clearly show any cost or opening-hour detail that still needs confirmation."
    )
    store = PlanRepository(repository.database, repository.registry)
    stays = {a.id: a for a in catalog.accommodation}
    if not stays:
        st.info("Add source-backed accommodation in Manage travel data before planning.")
        return
    places = {p.id: p for p in catalog.places if p.category != "area"}
    defaults = [
        key for key in ("al-seef", "dubai-frame", "shindagha", "dubai-mall") if key in places
    ]
    with st.form("trip-request"):
        start = st.date_input("First trip day", value=max(date.today(), date(2026, 11, 20)))
        days = st.number_input("Trip days", min_value=1, max_value=7, value=4)
        nights = st.number_input("Hotel nights", min_value=0, max_value=30, value=3)
        check_in = st.date_input("Hotel check-in", value=max(date.today(), date(2026, 11, 20)))
        adults = st.number_input("Adults", min_value=1, max_value=20, value=1)
        st.caption("Children by age band")
        child_counts = st.columns(4)
        child_bands = {
            band: child_counts[index].number_input(band, 0, 10, 0)
            for index, band in enumerate(("0-2", "3-5", "6-12", "13-17"))
        }
        rooms = st.number_input("Rooms", min_value=1, max_value=20, value=1)
        budget = st.text_input("Total trip budget (AED)", "5000")
        stay_id = st.selectbox(
            "Accommodation",
            list(stays),
            index=list(stays).index("rove-marina-quote-flex")
            if "rove-marina-quote-flex" in stays
            else 0,
            format_func=lambda key: stays[key].name,
        )
        selection = st.multiselect(
            "Places to consider (empty = automatic selection)",
            list(places),
            default=defaults,
            format_func=lambda key: places[key].name,
        )
        transport = st.multiselect(
            "Transport preferences", ["taxi", "walk", "transit", "abra"], default=["taxi"]
        )
        estimates = st.checkbox(
            "Accept disclosed planning allowances and projected opening hours", value=False
        )
        st.caption(
            "Optional allowances: meals AED 30–80 each; selected adult tickets base to base×1.05+10; taxi per traveler ceil(km×2.5+15) to ceil(km×4+35). Fee reserves are estimates, not guaranteed prices. Projected hours currently cover only 20–23 November 2026. Hotel snapshots expire after one day."
        )
        st.caption(
            "This local example starts and ends at the accommodation area. Flights, airport transfers, visas, shopping and personal incidentals are excluded. No accessibility guarantee."
        )
        generate = st.form_submit_button("Create my itinerary", type="primary")
    if generate:
        try:
            request = TripRequest(
                id="trip-" + uuid4().hex,
                days=days,
                nights=nights,
                arrival=start,
                departure=start + timedelta(days=days - 1),
                check_in=check_in if nights else None,
                check_out=check_in + timedelta(days=nights) if nights else None,
                travelers=dict(
                    adults=adults,
                    child_age_bands=[
                        band for band, count in child_bands.items() for _ in range(count)
                    ],
                ),
                rooms=rooms,
                budget=budget,
                budget_scope="total_trip",
                candidate_ids=selection,
                transport_preferences=transport,
                accept_planning_estimates=estimates,
                price_choices={
                    p.entity_id: p.id
                    for p in catalog.prices
                    if estimates and p.id in {"allowance-dubai-frame", "allowance-shindagha"}
                },
                meal_allowance_price_id="price-meal-allowance"
                if estimates and any(p.id == "price-meal-allowance" for p in catalog.prices)
                else None,
                exclusions=[
                    "flights",
                    "airport transfers",
                    "visas",
                    "shopping",
                    "personal incidentals",
                ],
                assumptions=[
                    "Trip starts/ends at the accommodation area; no live availability or accessibility guarantee."
                ]
                + (
                    [
                        "Accepted meal, taxi and ticket-fee allowances and recurring-hours projections as displayed in the request form; these are not guaranteed prices or opening times."
                    ]
                    if estimates
                    else []
                ),
            )
            result = plan_local(
                request,
                catalog,
                registry=repository.registry,
                base_id=stays[stay_id].area_id,
                accommodation_id=stay_id,
            )
            st.session_state["planner_result"] = result.model_dump_json()
        except (ValueError, OSError) as exc:
            st.session_state.pop("planner_result", None)
            st.error(str(exc))
    if st.session_state.get("planner_result"):
        result = PlanResult.model_validate_json(st.session_state["planner_result"])
        show_plan(result, store, catalog=catalog)
        label = st.text_input("Save this itinerary as", "Dubai trip")
        if st.button("Save itinerary"):
            try:
                store.save(result, label)
                st.success("Saved locally. Saving does not refresh evidence or confirm a booking.")
            except (ValueError, OSError, sqlite3.Error) as exc:
                st.error(str(exc))


def saved_plans(repository, catalog):
    st.header("Saved itineraries")
    store = PlanRepository(repository.database, repository.registry)
    rows = store.list()
    if not rows:
        st.info("No saved itineraries yet. Generate a trip, then choose Save itinerary.")
        return
    by_id = {row["id"]: row for row in rows}
    selected = st.selectbox(
        "Saved itinerary",
        list(by_id),
        format_func=lambda key: by_id[key]["label"] + " — " + by_id[key]["created_at"],
    )
    try:
        result = store.load(selected)
        if st.button("Recheck with current data"):
            if not result.accommodation:
                raise ValueError("Choose accommodation in Plan a trip before rechecking")
            stay = result.accommodation[0]
            fresh = plan_local(
                result.request,
                catalog,
                registry=repository.registry,
                base_id=stay.area_id,
                accommodation_id=stay.id,
            )
            st.session_state["planner_result"] = fresh.model_dump_json()
            st.info("Rechecked result is ready in Plan a trip. The saved snapshot was preserved.")
        show_plan(result, store, catalog=catalog, historical=True)
    except (ValueError, OSError, sqlite3.Error) as exc:
        st.error(str(exc))
