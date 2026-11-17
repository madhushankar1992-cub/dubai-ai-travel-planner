from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from threading import Barrier, Event

import pytest

from dubai_planner.agents.fixtures import FixtureSpecialist
from dubai_planner.domain.requests import TripRequest
from dubai_planner.observability.event_sink import EventSink, merge_records
from dubai_planner.orchestration.interface import RunContext
from dubai_planner.orchestration.langgraph_runner import LangGraphRunner


def request():
    return TripRequest.model_validate_json(Path("evaluation/phase2-request.json").read_text())


def context(catalog, **changes):
    values = dict(
        run_id="fixture-test",
        deadline=datetime.now(timezone.utc) + timedelta(seconds=30),
        cancelled=Event(),
        configuration_hash="test",
        dataset_version=catalog.dataset_version,
        prompt_version="fixtures-v1",
    )
    return RunContext(**(values | changes))


def run(catalog, registry, now, *, trip=None, specialists=None, ctx=None, **kwargs):
    events = []
    result = LangGraphRunner(
        catalog,
        registry,
        base_id="area-dubai-marina",
        accommodation_id="rove-marina-quote-flex",
        evidence_now=now,
        specialists=specialists,
        **kwargs,
    ).run(trip or request(), ctx or context(catalog), events.append)
    return result, events


def agents(**overrides):
    return {
        role: overrides.get(role, FixtureSpecialist(role))
        for role in ("orchestrator", "destination", "logistics", "budget", "reviewer")
    }


class BrokenLogistics(FixtureSpecialist):
    def __init__(self, mode):
        super().__init__("logistics")
        self.mode = mode

    def execute(self, request, context):
        output = super().execute(request, context)
        if context.stage == "schedule" and (context.revision == 0 or self.mode != "once"):
            activity = output.days[0].activities[0]
            if self.mode == "duplicate":
                if context.revision == 0:
                    copied = activity.model_copy(deep=True)
                    copied.id += "-duplicate"
                    output.days[0].activities.append(copied)
            else:
                activity.participants += 1 + (context.revision if self.mode == "changing" else 0)
        return output


def test_real_parallel_branches_join_and_contracts(catalog, registry, now):
    barrier = Barrier(2)

    class Paired(FixtureSpecialist):
        def execute(self, request, context):
            if context.stage in {"research", "preliminary"}:
                barrier.wait(timeout=5)
            return super().execute(request, context)

    result, events = run(
        catalog,
        registry,
        now,
        specialists=agents(destination=Paired("destination"), logistics=Paired("logistics")),
    )
    assert result.status == "validated_estimate"
    assert result.revisions == 0
    ready = {e.task_id: e.sequence for e in events if e.kind == "artifact_ready"}
    selected = next(
        e.sequence for e in events if e.kind == "agent_started" and e.task_id == "planner"
    )
    assert max(ready["destination"], ready["preliminary"]) < selected
    assert ready["scheduler"] < ready["costing"] < ready["review"]
    assert result.metrics["model_calls"] == result.metrics["travel_api_calls"] == 0
    assert len(result.sources) == len(catalog.evidence)


def test_needs_input_never_starts_research(catalog, registry, now):
    trip = request().model_copy(update={"budget": None})
    result, events = run(catalog, registry, now, trip=trip)
    assert result.status == "needs_input"
    assert not any(
        e.task_id in {"destination", "preliminary", "planner", "scheduler"} for e in events
    )


@pytest.mark.parametrize("mode", ["once", "duplicate"])
def test_repaired_violation_gets_new_schedule_cost_and_review(catalog, registry, now, mode):
    result, events = run(
        catalog, registry, now, specialists=agents(logistics=BrokenLogistics(mode))
    )
    assert result.status == "validated_estimate"
    assert result.revisions == 1
    assert result.metrics["reviews"] == 2
    assert result.request == request()
    for task in ("scheduler", "costing", "review"):
        artifacts = [e for e in events if e.task_id == task and e.kind == "artifact_ready"]
        assert [e.revision for e in artifacts] == [0, 1]
        assert artifacts[0].artifact_ids != artifacts[1].artifact_ids
    assert any(e.kind == "plan_changed" for e in events)


@pytest.mark.parametrize(
    "mode,reason,revisions", [("unchanged", "no_progress", 1), ("changing", "revision_limit", 2)]
)
def test_loop_termination(catalog, registry, now, mode, reason, revisions):
    result, events = run(
        catalog, registry, now, specialists=agents(logistics=BrokenLogistics(mode))
    )
    assert result.status == "partial"
    assert result.metrics["stop_reason"] == reason
    assert result.revisions == revisions
    assert result.metrics["reviews"] == revisions + 1
    assert len([e for e in events if e.kind == "run_completed"]) == 1


@pytest.mark.parametrize(
    "scenario", ["expired", "opt_out", "missing_route", "missing_price", "constraint"]
)
def test_evidence_gaps_are_not_repaired_with_invented_facts(catalog, registry, now, scenario):
    trip = request()
    original = catalog.model_dump_json()
    changed = catalog.model_copy(deep=True)
    if scenario == "expired":
        now += timedelta(days=2)
    elif scenario == "opt_out":
        trip.accept_planning_estimates = False
    elif scenario == "missing_route":
        payload = changed.model_dump()
        route_ids = {r.id for r in changed.routes}
        payload["routes"] = []
        payload["prices"] = [p for p in payload["prices"] if p["entity_id"] not in route_ids]
        changed = type(catalog).model_validate(payload)
    elif scenario == "missing_price":
        payload = changed.model_dump()
        payload["prices"] = []
        for record in [*payload["accommodation"], *payload["routes"]]:
            record["price_id"] = None
        changed = type(catalog).model_validate(payload)
    else:
        from dubai_planner.domain.requests import Constraint

        trip.constraints = [
            Constraint(
                id="unsupported", field="temperature", operator="eq", value="cool", priority="hard"
            )
        ]
    result, _ = run(changed, registry, now, trip=trip)
    assert result.status == "partial"
    assert result.metrics["stop_reason"] == "unresolved_evidence_or_constraint"
    assert result.revisions == 0
    assert catalog.model_dump_json() == original


@pytest.mark.parametrize(
    "limit,expected",
    [
        ("execution", "execution_limit"),
        ("graph", "graph_limit"),
        ("deadline", "deadline"),
        ("cancel", "cancelled"),
    ],
)
def test_resource_limits(catalog, registry, now, limit, expected):
    ctx, kwargs = context(catalog), {}
    if limit == "execution":
        kwargs["execution_limit"] = 2
    elif limit == "graph":
        kwargs["recursion_limit"] = 2
    elif limit == "deadline":
        ctx = context(catalog, deadline=datetime.now(timezone.utc) - timedelta(seconds=1))
    else:
        ctx.cancelled.set()
    result, _ = run(catalog, registry, now, ctx=ctx, **kwargs)
    assert result.status == ("cancelled" if limit == "cancel" else "failed")
    assert result.metrics["stop_reason"] == expected


def test_reducers_and_event_retries(catalog):
    evidence = catalog.evidence[0]
    assert merge_records([evidence], [evidence]) == [evidence]
    with pytest.raises(ValueError, match="Conflicting"):
        merge_records([evidence], [evidence.model_copy(update={"attribution": "changed"})])
    emitted = []
    sink = EventSink("test-run", emitted.append)
    first = sink.emit("artifact_ready", "logistics", 0, ["schedule-r0"])
    assert sink.emit("artifact_ready", "logistics", 0, ["schedule-r0"]) == first
    sink.emit("artifact_ready", "logistics", 1, ["schedule-r1"])
    assert len(emitted) == 2
    assert len(merge_records([first], [first])) == 1


def test_budget_repair_uses_real_alternative(catalog, registry, now):
    trip = request().model_copy(update={"budget": Decimal("4140")})
    trip = TripRequest.model_validate(trip.model_dump())
    result, _ = run(catalog, registry, now, trip=trip)
    assert result.status == "validated_estimate"
    assert result.revisions == 1
    assert result.accommodation[0].id == "rove-marina-quote-nonrefund"
    assert result.request.budget == trip.budget


def test_zero_revisions_preserves_failure(catalog, registry, now):
    result, events = run(
        catalog,
        registry,
        now,
        max_revisions=0,
        specialists=agents(logistics=BrokenLogistics("once")),
    )
    assert result.status == "partial"
    assert result.revisions == 0
    assert result.metrics["stop_reason"] == "revision_limit"
    assert not any(e.kind == "revision_started" for e in events)


def test_cancel_during_branch_discards_late_success(catalog, registry, now):
    ctx = context(catalog)

    class Cancelling(FixtureSpecialist):
        def execute(self, request, context):
            output = super().execute(request, context)
            ctx.cancelled.set()
            return output

    result, events = run(
        catalog, registry, now, ctx=ctx, specialists=agents(destination=Cancelling("destination"))
    )
    assert result.status == "cancelled"
    assert not any(e.task_id == "select" for e in events)


@pytest.mark.parametrize("tamper", ["request", "price", "exception", "candidate"])
def test_invalid_fixture_outputs_fail_without_leaking_payload(catalog, registry, now, tamper):
    role = {
        "request": "orchestrator",
        "price": "budget",
        "exception": "reviewer",
        "candidate": "destination",
    }[tamper]

    class Invalid(FixtureSpecialist):
        def execute(self, trip, context):
            output = super().execute(trip, context)
            if tamper == "request":
                output.request.budget = Decimal("999999")
            elif tamper == "price":
                output.budget.known_subtotal += Decimal("1")
            elif tamper == "candidate":
                output.candidates[0].name = "invented secret-token"
            else:
                raise RuntimeError("secret-token")
            return output

    result, events = run(catalog, registry, now, specialists=agents(**{role: Invalid(role)}))
    assert result.status == "failed"
    assert "secret-token" not in result.model_dump_json()
    assert all("secret-token" not in e.model_dump_json() for e in events)


def test_source_revocation_blocks_graph(catalog, registry, now):
    registry.policies[catalog.evidence[0].source_id].approved = False
    result, events = run(catalog, registry, now)
    assert result.status == "failed"
    assert not any(e.task_id == "parse" for e in events)
