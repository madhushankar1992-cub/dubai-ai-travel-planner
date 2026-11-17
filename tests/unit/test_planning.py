from decimal import Decimal

from dubai_planner.domain.itinerary import (
    ActivitySlot,
    BreakSlot,
    DayPlan,
    RelativeWindow,
    RouteLeg,
)
from dubai_planner.domain.money import BudgetSummary
from dubai_planner.domain.requests import Constraint
from dubai_planner.services.candidate_selection import select_candidates
from dubai_planner.services.planner import plan_local
from dubai_planner.services.scheduling import build_schedule, minutes, route_minutes
from dubai_planner.services.validation import outcome, validate_plan


def test_filtering_and_reproducibility(catalog, request_model, now):
    request_model.exclusions.append("al-fahidi")
    candidates = select_candidates(request_model, catalog, now=now)
    assert len(candidates) <= 20
    assert "al-fahidi" not in {p.id for p in candidates}
    assert candidates == select_candidates(request_model, catalog, now=now)
    request_model.mobility_needs = ["wheelchair access"]
    assert not select_candidates(request_model, catalog, now=now)


def test_schedule_limits_and_breaks(catalog, request_model, now):
    candidates = select_candidates(request_model, catalog, now=now)
    days = build_schedule(request_model, candidates, catalog, base_id="area-bur-dubai", now=now)
    assert len(days) == 4
    for day in days:
        if day.activities:
            assert day.breaks
        for a, b in zip(day.activities, day.activities[1:]):
            assert minutes(a.window)[1] <= minutes(b.window)[0]
    route = catalog.routes[0]
    assert route.includes_contingency
    assert route_minutes(route, Decimal("0.20")) == route.duration_max
    route.includes_contingency = False
    assert route_minutes(route, Decimal("0.20")) > route.duration_max


def test_typed_runner_no_network(catalog, registry, request_model, now, monkeypatch):
    import socket

    from dubai_planner.domain.review import PlanResult

    def fail(*args, **kwargs):
        raise AssertionError("Network call during deterministic planning")

    monkeypatch.setattr(socket.socket, "connect", fail)
    result = plan_local(request_model, catalog, registry=registry, now=now)
    assert result.status == "partial"
    assert len(result.days) == 4 and result.metrics["model_calls"] == 0
    assert result.budget.compliance == "unknown"
    assert result == plan_local(request_model, catalog, registry=registry, now=now)
    assert PlanResult.model_validate_json(result.model_dump_json()) == result
    assert {f.rule_id for f in result.findings} >= {"HOURS_UNKNOWN", "BUDGET_UNKNOWN"}


def test_needs_input(catalog, registry, request_model, now):
    request_model.budget_scope = None
    assert plan_local(request_model, catalog, registry=registry, now=now).status == "needs_input"


def test_seeded_violations_are_not_erased(catalog, request_model, now):
    request_model.days = 1
    request_model.nights = 0
    request_model.exclusions.append("al-fahidi")

    def slot(sid, start, end):
        return ActivitySlot(
            id=sid,
            place_id="al-fahidi",
            window=RelativeWindow(day=1, start_minute=start, end_minute=end),
            participants=1,
            evidence_ids=["ev-culture"],
            hours_check="checked",
        )

    day = DayPlan(
        day=1,
        base_assumption="area-bur-dubai",
        activities=[slot("a", 600, 720), slot("b", 700, 800)],
    )
    budget = BudgetSummary(
        cap="5000", total_low="100", total_high="100", compliance="within_estimate"
    )
    findings = validate_plan(
        request_model, [day], budget, catalog, base_id="area-bur-dubai", now=now
    )
    rules = {f.rule_id for f in findings}
    assert rules >= {
        "ACTIVITY_OVERLAP",
        "DUPLICATE_ACTIVITY",
        "HARD_EXCLUSION",
        "ROUTE_MISSING",
        "HOURS_UNKNOWN",
    }
    assert outcome(request_model, findings) == "partial"


def test_applicable_hours_and_travel_validation(catalog, request_model, now):
    from dubai_planner.domain.places import OpeningWindow
    from dubai_planner.services.scheduling import window

    request_model.days = 1
    request_model.nights = 0
    request_model.arrival = "2026-11-05"
    request_model.departure = "2026-11-05"
    place = next(p for p in catalog.places if p.id == "dubai-frame")
    place.opening_windows = [
        OpeningWindow(
            weekday=3,
            start_minute=480,
            end_minute=1260,
            valid_from="2026-11-05",
            valid_to="2026-11-05",
            evidence_ids=["ev-frame"],
        )
    ]
    slot = ActivitySlot(
        id="visit",
        place_id=place.id,
        window=window(request_model, 1, 600, 720),
        participants=1,
        hours_check="checked",
        evidence_ids=["ev-frame"],
    )
    # Explicit synthetic supported routes, never added to the production catalog.
    routes = [
        RouteLeg(
            id="synthetic-out",
            origin_id="area-bur-dubai",
            destination_id=place.id,
            mode="taxi",
            duration_min=15,
            duration_max=20,
            method="SYNTHETIC",
            feasibility_supported=True,
            evidence_ids=["ev-editorial"],
        ),
        RouteLeg(
            id="synthetic-back",
            origin_id=place.id,
            destination_id="area-bur-dubai",
            mode="taxi",
            duration_min=15,
            duration_max=20,
            method="SYNTHETIC",
            feasibility_supported=True,
            evidence_ids=["ev-editorial"],
        ),
    ]
    catalog.routes.extend(routes)
    day = DayPlan(
        day=1,
        base_assumption="SYNTHETIC",
        activities=[slot],
        routes=routes,
        breaks=[BreakSlot(kind="meal", window=window(request_model, 1, 735, 780))],
    )
    budget = BudgetSummary(
        cap="5000", total_low="100", total_high="100", compliance="within_estimate"
    )
    findings = validate_plan(
        request_model, [day], budget, catalog, base_id="area-bur-dubai", now=now
    )
    assert not findings
    slot.window = window(request_model, 1, 600, 1300)
    rules = {
        f.rule_id
        for f in validate_plan(
            request_model, [day], budget, catalog, base_id="area-bur-dubai", now=now
        )
    }
    assert {"VENUE_CLOSED", "DAY_BOUNDARY", "BREAK_OVERLAP"} <= rules


def test_unsupported_hard_constraints_block_success(catalog, request_model, now):
    request_model.constraints = [
        Constraint(id="diet", field="dietary", operator="eq", value="vegan")
    ]
    findings = validate_plan(request_model, [], None, catalog, base_id="area-bur-dubai", now=now)
    assert "CONSTRAINT_UNVERIFIED" in {f.rule_id for f in findings}
