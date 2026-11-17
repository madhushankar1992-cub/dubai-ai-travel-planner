"""Independent rule checks; qualitative review may add findings, never remove these."""

from datetime import timedelta
from decimal import Decimal

from dubai_planner.domain.itinerary import DatedWindow
from dubai_planner.domain.review import ReviewFinding

from .candidate_selection import accessibility_supported, excluded
from .evidence import evidence_index, usable
from .scheduling import minutes, operating_window, route_minutes


def finding(rule, message, entities=(), *, owner="logistics", refs=(), hard=True):
    return ReviewFinding(
        rule_id=rule,
        severity="error" if hard else "warning",
        entity_ids=list(entities),
        evidence_ids=list(refs),
        owner=owner,
        message=message,
        proposed_action="Resolve the constraint or obtain applicable evidence, then recompute.",
        hard=hard,
    )


def validate_plan(
    request,
    days,
    budget,
    catalog,
    *,
    base_id,
    accommodation=None,
    activity_buffer=15,
    travel_contingency=Decimal("0.20"),
    now=None,
):
    findings = []
    evidence = evidence_index(catalog)
    places = {p.id: p for p in catalog.places}
    seen = set()
    if request.clarification_fields():
        findings.append(
            finding(
                "INPUT_REQUIRED", ", ".join(request.clarification_fields()), owner="orchestrator"
            )
        )
    if sorted(d.day for d in days) != list(range(1, request.days + 1)):
        findings.append(finding("DAY_COUNT", "Days must exactly match the request"))
    if request.confirmed_nights:
        if not accommodation or accommodation.max_occupancy is None:
            findings.append(
                finding("OCCUPANCY_UNKNOWN", "Confirm property occupancy for the party")
            )
        elif accommodation.max_occupancy * request.rooms < request.travelers.total:
            findings.append(finding("OCCUPANCY_EXCEEDED", "Party exceeds room capacity"))
        if accommodation:
            if accommodation.max_adults is not None and (
                request.travelers.adults > accommodation.max_adults * request.rooms
            ):
                findings.append(finding("OCCUPANCY_EXCEEDED", "Party exceeds adult capacity"))
            children = request.travelers.child_age_bands
            if accommodation.max_children is not None and (
                len(children) > accommodation.max_children * request.rooms
            ):
                findings.append(finding("OCCUPANCY_EXCEEDED", "Party exceeds child capacity"))
            if accommodation.verified_child_age_bands is not None and any(
                band not in accommodation.verified_child_age_bands for band in children
            ):
                findings.append(
                    finding("OCCUPANCY_UNKNOWN", "Confirm child ages against room eligibility")
                )
            if not usable(accommodation.evidence_ids, evidence, on_date=request.check_in, now=now):
                findings.append(finding("OCCUPANCY_UNKNOWN", "Accommodation evidence is outdated"))
    for day in days:
        for route in day.routes:
            fields = (
                "origin_id",
                "destination_id",
                "mode",
                "duration_min",
                "duration_max",
                "feasibility_supported",
                "includes_contingency",
                "evidence_ids",
                "status",
            )
            if not any(
                all(getattr(route, field) == getattr(source, field) for field in fields)
                for source in catalog.routes
            ):
                findings.append(
                    finding(
                        "ROUTE_NOT_IN_CATALOG",
                        "Route facts differ from approved evidence",
                        [route.id],
                    )
                )
        if not day.activities:
            findings.append(finding("EMPTY_DAY", f"Day {day.day} has no activities"))
        on_date = request.arrival + timedelta(days=day.day - 1) if request.arrival else None
        start_limit = request.arrival_minute if day.day == 1 else 540
        end_limit = request.departure_minute if day.day == request.days else 1200
        previous_end, previous_id = start_limit, base_id
        for activity in day.activities:
            start, end = minutes(activity.window)
            place = places.get(activity.place_id)
            if activity.place_id in seen:
                findings.append(
                    finding("DUPLICATE_ACTIVITY", "Repeated place", [activity.place_id])
                )
            seen.add(activity.place_id)
            if on_date and (
                not isinstance(activity.window, DatedWindow)
                or activity.window.start.date() != on_date
                or activity.window.end.date() != on_date
            ):
                findings.append(
                    finding(
                        "ACTIVITY_DATE", "Activity does not match the requested day", [activity.id]
                    )
                )
            if not on_date and isinstance(activity.window, DatedWindow):
                findings.append(
                    finding(
                        "ACTIVITY_DATE", "Undated requests require relative slots", [activity.id]
                    )
                )
            if start < previous_end:
                findings.append(
                    finding(
                        "ACTIVITY_OVERLAP",
                        "Visits overlap or lack the configured buffer",
                        [activity.id],
                    )
                )
            if start < start_limit or end > end_limit:
                findings.append(
                    finding(
                        "DAY_BOUNDARY",
                        "Visit exceeds arrival/departure or daily limits",
                        [activity.id],
                    )
                )
            if activity.participants != request.travelers.total:
                findings.append(
                    finding(
                        "PARTICIPANTS", "Activity party count differs from request", [activity.id]
                    )
                )
            if not place:
                findings.append(
                    finding(
                        "UNKNOWN_PLACE",
                        "Place is not in the approved catalog",
                        [activity.place_id],
                        owner="destination",
                    )
                )
            else:
                if place.destination != request.destination or excluded(place, request):
                    findings.append(
                        finding(
                            "HARD_EXCLUSION",
                            "Selected place violates destination or exclusion",
                            [place.id],
                            owner="destination",
                        )
                    )
                if request.mobility_needs and not accessibility_supported(
                    place, request, evidence, now, on_date
                ):
                    findings.append(
                        finding(
                            "ACCESSIBILITY_UNKNOWN",
                            "Required accessibility lacks usable evidence",
                            [place.id],
                        )
                    )
                windows = operating_window(
                    place, on_date, evidence, now, allow_estimated=request.accept_planning_estimates
                )
                if not windows:
                    findings.append(
                        finding(
                            "HOURS_UNKNOWN",
                            "No applicable operating window; prose hours are insufficient",
                            [place.id],
                        )
                    )
                elif not any(w.start_minute <= start and end <= w.end_minute for w in windows):
                    findings.append(
                        finding(
                            "VENUE_CLOSED", "Visit is outside supported operating hours", [place.id]
                        )
                    )
                if end - start < place.visit_minutes_min:
                    findings.append(
                        finding(
                            "VISIT_DURATION",
                            "Visit is shorter than the minimum allowance",
                            [place.id],
                        )
                    )
            if not usable(activity.evidence_ids, evidence, on_date=on_date, now=now):
                findings.append(
                    finding(
                        "UNSUPPORTED_FACT",
                        "Missing, stale or inapplicable activity evidence",
                        [activity.id],
                        refs=activity.evidence_ids,
                    )
                )
            matching = [
                r
                for r in day.routes
                if r.origin_id == previous_id and r.destination_id == activity.place_id
            ]
            findings.extend(
                check_leg(
                    matching,
                    previous_id,
                    activity.place_id,
                    previous_end,
                    start,
                    request,
                    evidence,
                    on_date,
                    now,
                    travel_contingency,
                )
            )
            previous_id, previous_end = activity.place_id, end + activity_buffer
        occupied = [(minutes(a.window), a.id) for a in day.activities]
        occupied += [(minutes(b.window), b.kind) for b in day.breaks]
        occupied.sort()
        if any(a[0][1] > b[0][0] for a, b in zip(occupied, occupied[1:])):
            findings.append(finding("BREAK_OVERLAP", "A meal/rest interval overlaps another slot"))
        for pause in day.breaks:
            a, b = minutes(pause.window)
            if a < start_limit or b > end_limit:
                findings.append(finding("DAY_BOUNDARY", "Break exceeds daily limits"))
        if not day.breaks:
            findings.append(finding("REST_MISSING", "No explicit meal/rest allowance"))
        if day.activities:
            previous_end = max([previous_end, *(minutes(b.window)[1] for b in day.breaks)])
            matching = [
                r for r in day.routes if r.origin_id == previous_id and r.destination_id == base_id
            ]
            findings.extend(
                check_leg(
                    matching,
                    previous_id,
                    base_id,
                    previous_end,
                    end_limit,
                    request,
                    evidence,
                    on_date,
                    now,
                    travel_contingency,
                )
            )
    expected_cap = request.budget
    if expected_cap is not None and request.budget_scope == "per_person":
        expected_cap *= request.travelers.total
    if budget is not None and budget.cap != expected_cap:
        findings.append(
            finding(
                "BUDGET_CAP_CHANGED",
                "Calculated budget cap differs from the request",
                owner="budget",
            )
        )
    if budget is None or budget.compliance == "unknown":
        findings.append(
            finding(
                "BUDGET_UNKNOWN", "Required costs, fees or scope remain unresolved", owner="budget"
            )
        )
    elif budget.compliance != "within_estimate":
        findings.append(
            finding(
                "BUDGET_EXCEEDED" if budget.compliance == "over_budget" else "BUDGET_AT_RISK",
                "Budget including contingency does not fit the cap",
                owner="budget",
            )
        )
    for c in request.constraints:
        if c.priority != "hard":
            continue
        if c.operator in {"excludes", "ne"} and c.field in {
            "place",
            "place_id",
            "category",
            "area",
            "interests",
        }:
            continue  # Each selected place was checked above.
        # General natural-language conditions cannot be silently treated as satisfied.
        findings.append(
            finding(
                "CONSTRAINT_UNVERIFIED",
                f"Explicit constraint {c.id} requires a supported evaluator",
                [c.id],
                owner="orchestrator",
            )
        )
    return findings


def check_leg(
    routes, origin, destination, earliest, latest, request, evidence, on_date, now, contingency
):
    entities = [origin, destination]
    if len(routes) != 1:
        return [
            finding(
                "ROUTE_MISSING" if not routes else "ROUTE_DUPLICATE",
                "Exactly one connecting leg is required",
                entities,
            )
        ]
    route = routes[0]
    findings = []
    if (
        route.status == "unknown"
        or not route.feasibility_supported
        or not usable(route.evidence_ids, evidence, on_date=on_date, now=now)
    ):
        findings.append(
            finding(
                "ROUTE_UNSUPPORTED",
                "Route existence/timing is unverified",
                [route.id],
                refs=route.evidence_ids,
            )
        )
    if earliest + route_minutes(route, contingency) > latest:
        findings.append(
            finding("TRAVEL_TIME", "Insufficient time for connecting travel", [route.id])
        )
    if request.transport_preferences and route.mode not in request.transport_preferences:
        findings.append(
            finding("TRANSPORT_MODE", "Route violates requested transport modes", [route.id])
        )
    return findings


def outcome(request, findings):
    if request.clarification_fields():
        return "needs_input"
    # A failed selected plan does not prove all available alternatives infeasible.
    return (
        "partial"
        if any(f.hard and f.severity == "error" for f in findings)
        else "validated_estimate"
    )
