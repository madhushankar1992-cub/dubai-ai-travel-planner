"""Local deterministic runner for Phases 0-3; no LLM or graph execution."""

import hashlib
from datetime import timedelta

from dubai_planner.domain.money import CostLine
from dubai_planner.domain.review import PlanResult

from .candidate_selection import select_candidates
from .costing import calculate_budget, quantity_for
from .evidence import evidence_index, price_usable, usable
from .scheduling import build_schedule
from .validation import outcome, validate_plan


def build_cost_lines(request, days, accommodation, catalog, *, now=None):
    lines, missing = [], []
    evidence = evidence_index(catalog)
    by_price = {p.id: p for p in catalog.prices}
    places = {p.id: p for p in catalog.places}

    def add_prices(entity_id, category, key, on_date, prices=None):
        options = (
            prices
            if prices is not None
            else [p for p in catalog.prices if p.entity_id == entity_id]
        )
        if entity_id in request.price_choices:
            options = [p for p in options if p.id == request.price_choices[entity_id]]
        elif prices is None:
            options = [p for p in options if not p.requires_opt_in]
        if not request.accept_planning_estimates:
            options = [p for p in options if not p.requires_opt_in]
        if not options:
            missing.append(key + ": no price evidence")
            return
        # Multiple unqualified prices are alternatives, never cumulative fees.
        unqualified = [p for p in options if p.age_category in (None, "all")]
        if len(unqualified) > 1 or (unqualified and len(options) > 1):
            missing.append(key + ": select an unambiguous price product")
            return
        covered_people = 0
        for price in options:
            if not usable(price.evidence_ids, evidence, on_date=on_date, now=now):
                missing.append(key + ": price evidence stale or inapplicable")
            if (price.applicable_from or price.applicable_to) and (
                on_date is None
                or (price.applicable_from and on_date < price.applicable_from)
                or (price.applicable_to and on_date > price.applicable_to)
            ):
                missing.append(key + ": quote dates do not cover travel")
            quantity = quantity_for(price, request)  # No assumed vehicle capacity.
            if category in {"activity", "food"}:
                covered_people += quantity or 0
            lines.append(
                CostLine(
                    id=f"{key}-{price.id}",
                    category=category,
                    price=price,
                    quantity=quantity,
                    coverage_ids=[f"{key}:{price.age_category or 'all'}"],
                )
            )
        if category in {"activity", "food"} and covered_people != request.travelers.total:
            missing.append(key + ": price eligibility does not cover exactly the party")

    if request.confirmed_nights:
        if accommodation and accommodation.price_id in by_price:
            add_prices(
                accommodation.id,
                "accommodation",
                "stay",
                request.check_in,
                [by_price[accommodation.price_id]],
            )
            quote = by_price[accommodation.price_id]
            if quote.applicable_to and (
                request.check_out is None
                or request.check_out - timedelta(days=1) > quote.applicable_to
            ):
                missing.append("stay: quote does not cover the entire stay")
        else:
            missing.append("accommodation: no selected quote")
    for day in days:
        on_date = request.arrival + timedelta(days=day.day - 1) if request.arrival else None
        meals = 0
        for slot in day.activities:
            place = places.get(slot.place_id)
            category = "food" if place and place.category == "restaurant" else "activity"
            meals += category == "food"
            add_prices(slot.place_id, category, slot.id, on_date)
        if meals < 3:
            allowance = by_price.get(request.meal_allowance_price_id)
            if (
                allowance
                and (not allowance.requires_opt_in or request.accept_planning_estimates)
                and allowance.unit == "per_person_meal"
                and allowance.age_category in (None, "all")
                and price_usable(allowance, evidence, on_date=on_date, now=now)
            ):
                lines.append(
                    CostLine(
                        id=f"day-{day.day}-remaining-meals",
                        category="food",
                        price=allowance,
                        quantity=quantity_for(allowance, request, occurrences=3 - meals),
                        coverage_ids=[f"day-{day.day}:remaining-meals"],
                        inclusions=[allowance.reason],
                    )
                )
            else:
                missing.append(
                    f"day-{day.day}: prices for {3 - meals} remaining meals per traveler"
                )
        for leg in day.routes:
            price = by_price.get(leg.price_id)
            if price:
                add_prices(price.entity_id, "transport", leg.id, on_date, [price])
            else:
                missing.append(f"{leg.id}: transport cost basis unavailable")
    return lines, missing


def plan_local(
    request, catalog, *, registry, base_id="area-bur-dubai", accommodation_id=None, now=None
):
    catalog.check_policy(registry, "read")
    run_id = (
        "local-"
        + hashlib.sha256(
            (
                request.model_dump_json()
                + catalog.dataset_version
                + base_id
                + str(accommodation_id)
            ).encode()
        ).hexdigest()[:16]
    )
    if request.clarification_fields():
        return PlanResult(
            run_id=run_id,
            graph_version="deterministic-v1",
            request=request,
            status="needs_input",
            assumptions=request.clarification_fields(),
        )
    accommodation = (
        next((a for a in catalog.accommodation if a.id == accommodation_id), None)
        if accommodation_id
        else next((a for a in catalog.accommodation if a.area_id == base_id), None)
    )
    if accommodation_id and accommodation is None:
        raise ValueError("Unknown accommodation selection")
    if accommodation and accommodation.area_id != base_id:
        raise ValueError("Accommodation and scheduling base must match")
    candidates = select_candidates(request, catalog, now=now)
    days = build_schedule(request, candidates, catalog, base_id=base_id, now=now)
    lines, missing = build_cost_lines(request, days, accommodation, catalog, now=now)
    budget = calculate_budget(lines, request, missing_required=missing)
    findings = validate_plan(
        request, days, budget, catalog, base_id=base_id, accommodation=accommodation, now=now
    )
    warnings = [
        e.id
        for e in catalog.evidence
        if not usable([e.id], evidence_index(catalog), on_date=request.arrival, now=now)
    ]
    return PlanResult(
        run_id=run_id,
        graph_version="deterministic-v1",
        request=request,
        status=outcome(request, findings),
        days=days,
        accommodation=[accommodation] if accommodation else [],
        budget=budget,
        findings=findings,
        validation_complete=True,
        sources=catalog.evidence,
        freshness_warnings=warnings,
        assumptions=[
            *request.assumptions,
            "Deterministic local planning; no model-driven agents.",
            "Three meals per day require pricing; property and route evidence may be incomplete.",
        ],
        metrics={
            "dataset_version": catalog.dataset_version,
            "candidates": len(candidates),
            "model_calls": 0,
            "travel_api_calls": 0,
        },
    )
