"""Deterministic conservative scheduling; missing route evidence stays unresolved."""

from datetime import datetime, time, timedelta
from decimal import ROUND_CEILING, Decimal
from zoneinfo import ZoneInfo

from dubai_planner.domain.itinerary import (
    ActivitySlot,
    BreakSlot,
    DatedWindow,
    DayPlan,
    RelativeWindow,
)

from .candidate_selection import cluster_candidates
from .evidence import evidence_index, usable


def window(request, day, start, end):
    if request.arrival:
        midnight = datetime.combine(
            request.arrival + timedelta(days=day - 1), time(), ZoneInfo("Asia/Dubai")
        )
        return DatedWindow(
            start=midnight + timedelta(minutes=start), end=midnight + timedelta(minutes=end)
        )
    return RelativeWindow(day=day, start_minute=start, end_minute=end)


def minutes(slot_window):
    if isinstance(slot_window, RelativeWindow):
        return slot_window.start_minute, slot_window.end_minute
    start, end = slot_window.start, slot_window.end
    return start.hour * 60 + start.minute, (
        end.date() - start.date()
    ).days * 1440 + end.hour * 60 + end.minute


def route_minutes(route, contingency):
    if route is None or route.duration_max is None:
        return 60  # A disclosed placeholder; validation still fails the missing leg.
    factor = Decimal(1) if route.includes_contingency else Decimal(1) + contingency
    return int((route.duration_max * factor).to_integral_value(rounding=ROUND_CEILING))


def find_route(catalog, origin, destination, preferences):
    modes = preferences or ["walk", "taxi", "transit", "abra"]
    return next(
        (
            r
            for mode in modes
            for r in catalog.routes
            if (r.origin_id, r.destination_id, r.mode) == (origin, destination, mode)
        ),
        None,
    )


def operating_window(place, on_date, evidence, now=None, *, allow_estimated=False):
    if on_date is None:
        return []
    return [
        w
        for w in place.opening_windows
        if w.weekday == on_date.weekday()
        and (not w.estimated or allow_estimated)
        and w.valid_from <= on_date <= w.valid_to
        and usable(w.evidence_ids, evidence, on_date=on_date, now=now)
    ]


def build_schedule(
    request,
    candidates,
    catalog,
    *,
    base_id,
    activity_buffer=15,
    travel_contingency=Decimal("0.20"),
    now=None,
):
    if type(activity_buffer) is not int or activity_buffer < 0:
        raise ValueError("Activity buffer must be a nonnegative integer")
    if (
        not isinstance(travel_contingency, Decimal)
        or not travel_contingency.is_finite()
        or travel_contingency < 0
    ):
        raise ValueError("Travel contingency must be a nonnegative finite Decimal")
    base = next((p for p in catalog.places if p.id == base_id and p.category == "area"), None)
    if base is None:
        raise ValueError("A catalog accommodation area is required")
    groups = list(cluster_candidates(candidates).values())
    pending = [p for group in groups for p in group if p.category == "attraction"]
    restaurants = [p for group in groups for p in group if p.category == "restaurant"]
    evidence = evidence_index(catalog)
    days = []
    for day in range(1, request.days + 1):
        start = request.arrival_minute if day == 1 else 540
        finish = request.departure_minute if day == request.days else 1200
        on_date = request.arrival + timedelta(days=day - 1) if request.arrival else None
        plan = DayPlan(
            day=day,
            base_assumption=f"{base.id}: approximate area centroid; property unconfirmed",
            meal_rest_notes=[
                f"Activity buffer {activity_buffer} min; travel contingency {travel_contingency:.0%} unless already included.",
                "Missing routes reserve 60 minutes provisionally and prevent validation.",
            ],
        )
        # Spread a small curated selection over all requested days.
        remaining_days = request.days - day + 1
        selected = pending[: min(2, max(1, len(pending) // remaining_days))]
        if selected:
            dining = next((p for p in restaurants if p.area == selected[0].area), None)
            if dining:
                selected.insert(1, dining)
        cursor, previous = start, base_id
        for place in selected:
            leg = find_route(catalog, previous, place.id, request.transport_preferences)
            arrival = cursor + route_minutes(leg, travel_contingency)
            windows = operating_window(
                place, on_date, evidence, now, allow_estimated=request.accept_planning_estimates
            )
            duration = place.visit_minutes_max
            if windows:
                fit = next(
                    (
                        w
                        for w in sorted(windows, key=lambda w: w.start_minute)
                        if max(arrival, w.start_minute) + duration <= w.end_minute
                    ),
                    None,
                )
                if fit is None:
                    continue
                arrival = max(arrival, fit.start_minute)
            return_leg = find_route(catalog, place.id, base_id, request.transport_preferences)
            if (
                arrival
                + duration
                + activity_buffer
                + 45
                + route_minutes(return_leg, travel_contingency)
                > finish
            ):
                continue
            refs = sorted({e for ids in place.field_evidence.values() for e in ids})
            refs += [e for w in windows for e in w.evidence_ids if e not in refs]
            plan.activities.append(
                ActivitySlot(
                    id=f"day-{day}-{place.id}",
                    place_id=place.id,
                    window=window(request, day, arrival, arrival + duration),
                    participants=request.travelers.total,
                    hours_check="checked" if windows else "unknown",
                    evidence_ids=refs,
                )
            )
            if leg:
                copy = leg.model_copy(deep=True)
                copy.id = f"day-{day}-{leg.id}"
                if request.arrival:
                    copy.departure = window(request, day, cursor, cursor + 1).start
                plan.routes.append(copy)
            cursor = arrival + duration + activity_buffer
            previous = place.id
            if place in pending:
                pending.remove(place)
            if place in restaurants:
                restaurants.remove(place)
        if plan.activities:
            has_meal = any(
                p.category == "restaurant" and p.id in {a.place_id for a in plan.activities}
                for p in candidates
            )
            plan.breaks.append(
                BreakSlot(
                    kind="rest" if has_meal else "meal",
                    window=window(request, day, cursor, cursor + 45),
                )
            )
            cursor += 45
            leg = find_route(catalog, previous, base_id, request.transport_preferences)
            if leg:
                copy = leg.model_copy(deep=True)
                copy.id = f"day-{day}-{leg.id}"
                if request.arrival:
                    copy.departure = window(request, day, cursor, cursor + 1).start
                plan.routes.append(copy)
        days.append(plan)
    return days
