"""Bounded, in-memory LangGraph runner using deterministic fixture specialists."""

from datetime import datetime, timezone
from threading import Lock
from typing import Annotated, TypedDict

from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph

from dubai_planner.agents.contracts import (
    BudgetOutput,
    DestinationOutput,
    LogisticsOutput,
    OrchestratorOutput,
    ReviewOutput,
)
from dubai_planner.agents.fixtures import FixtureContext, FixtureSpecialist
from dubai_planner.domain.events import ExecutionEvent
from dubai_planner.domain.itinerary import DayPlan
from dubai_planner.domain.money import BudgetSummary
from dubai_planner.domain.places import Evidence
from dubai_planner.domain.review import PlanResult, ReviewFinding
from dubai_planner.observability.event_sink import EventSink, merge_records
from dubai_planner.orchestration.revision_policy import decision, fingerprint
from dubai_planner.services.evidence import evidence_index, usable
from dubai_planner.services.planner import plan_local
from dubai_planner.services.validation import outcome, validate_plan

GRAPH_VERSION = "fixture-langgraph-v2"


class GraphState(TypedDict, total=False):
    # Only the two research branches write concurrently, to different scalar keys.
    parsed: OrchestratorOutput
    destination: DestinationOutput
    preliminary: LogisticsOutput
    selected: OrchestratorOutput
    repair: dict
    days: list[DayPlan]
    budget: BudgetSummary
    budget_alternatives: list[str]
    findings: list[ReviewFinding]
    revision: int
    history: list[str]
    stop_reason: str
    owners: list[str]
    result: PlanResult
    evidence: Annotated[list[Evidence], merge_records]
    events: Annotated[list[ExecutionEvent], merge_records]


class RunStopped(Exception):
    pass


class LangGraphRunner:
    def __init__(
        self,
        catalog,
        registry,
        *,
        base_id="area-bur-dubai",
        accommodation_id=None,
        max_revisions=2,
        execution_limit=40,
        recursion_limit=50,
        specialists=None,
        evidence_now=None,
        mode="fixture",
        model_metrics=lambda: {},
        model_summaries=lambda: [],
    ):
        if type(max_revisions) is not int or not 0 <= max_revisions <= 2:
            raise ValueError("Revision limit must be 0–2")
        if execution_limit < 1 or recursion_limit < 1:
            raise ValueError("Execution limits must be positive")
        self.catalog, self.registry = catalog, registry
        self.base_id, self.accommodation_id = base_id, accommodation_id
        self.max_revisions = max_revisions
        self.execution_limit, self.recursion_limit = execution_limit, recursion_limit
        self.specialists = (
            dict(specialists)
            if specialists
            else {
                role: FixtureSpecialist(role)
                for role in (
                    "orchestrator",
                    "destination",
                    "logistics",
                    "planner",
                    "scheduler",
                    "budget",
                    "reviewer",
                )
            }
        )
        # Existing custom Phase 4 specialists remain valid while the production graph
        # gets dedicated planner and scheduler roles.
        self.specialists.setdefault("planner", self.specialists["orchestrator"])
        self.specialists.setdefault("scheduler", self.specialists["logistics"])
        self.evidence_now = evidence_now
        if mode not in {"fixture", "model"} or (mode == "model" and not specialists):
            raise ValueError("Model mode requires explicit specialists")
        self.mode = mode
        self.graph_version = GRAPH_VERSION if mode == "fixture" else "model-langgraph-v2"
        self.model_metrics, self.model_summaries = model_metrics, model_summaries

    def run(self, request, context, emit_event):
        request = request.model_copy(deep=True)
        catalog = self.catalog.model_copy(deep=True)
        now = self.evidence_now or datetime.now(timezone.utc)
        sink = EventSink(context.run_id, emit_event)
        last_reviewed = None
        calls = 0
        lock = Lock()

        def guard(*, count=False):
            nonlocal calls
            with lock:
                if context.cancelled.is_set():
                    raise RunStopped("cancelled")
                if datetime.now(timezone.utc) >= context.deadline:
                    raise RunStopped("deadline")
                if count:
                    if calls >= self.execution_limit:
                        raise RunStopped("execution_limit")
                    calls += 1

        def options(state):
            repair = state.get("repair", {})
            stays = state.get("preliminary", LogisticsOutput(accommodation=[])).accommodation
            stay_id = repair.get("accommodation_id")
            if stay_id:
                stays = [next(a for a in catalog.accommodation if a.id == stay_id)]
            base = stays[0].area_id if stays else self.base_id
            return stays, base

        def invoke(role, stage, state, output):
            guard()
            stays, base = options(state)
            available = state.get("destination", DestinationOutput(candidates=[])).candidates
            selected = state.get("selected")
            if selected and stage != "plan":
                available = [p for p in available if p.id in selected.selected_ids]
            if "candidate_ids" in state.get("repair", {}):
                available = [p for p in available if p.id in state["repair"]["candidate_ids"]]
            ctx = FixtureContext(
                catalog=catalog.model_copy(deep=True),
                base_id=base,
                accommodation_id=self.accommodation_id,
                now=now,
                revision=state.get("revision", 0),
                stage=stage,
                candidates=available,
                accommodation=stays,
                days=state.get("days", []),
                budget=state.get("budget"),
                findings=state.get("findings", []),
            )
            result = self.specialists[role].execute(
                request.model_copy(deep=True), ctx.model_copy(deep=True)
            )
            guard()
            return output.model_validate(result.model_dump())

        def result_for(state, reason):
            stays, _ = options(state)
            findings = state.get("findings", [])
            status = "needs_input" if request.clarification_fields() else outcome(request, findings)
            return PlanResult(
                run_id=context.run_id,
                graph_version=self.graph_version,
                request=request,
                status=status,
                days=state.get("days", []),
                accommodation=stays,
                budget=state.get("budget"),
                findings=findings,
                validation_complete=bool("findings" in state),
                revisions=state.get("revision", 0),
                sources=state.get("evidence", []),
                freshness_warnings=[
                    e.id
                    for e in catalog.evidence
                    if not usable([e.id], evidence_index(catalog), on_date=request.arrival, now=now)
                ],
                assumptions=[
                    *request.assumptions,
                    *request.clarification_fields(),
                    "Fixture agents only; no model inference or live travel services."
                    if self.mode == "fixture"
                    else "Groq planning agents and Gemini review; approved local travel evidence, no live inventory.",
                    "Evidence evaluated at " + now.isoformat(),
                ],
                metrics={
                    "dataset_version": catalog.dataset_version,
                    "graph_version": self.graph_version,
                    "schema_version": "1.0",
                    "prompt_version": context.prompt_version,
                    "validator_version": "deterministic-v1",
                    "model_calls": 0,
                    "travel_api_calls": 0,
                    "node_calls": calls,
                    "stop_reason": reason,
                    "reviews": state.get("revision", 0) + 1 if "findings" in state else 0,
                    "configuration_hash": context.configuration_hash,
                },
            )

        def parse(state):
            output = invoke("orchestrator", "parse", state, OrchestratorOutput)
            if (
                output.request != request
                or output.clarification_fields != request.clarification_fields()
            ):
                raise ValueError("Fixture parse changed request or clarification requirements")
            return {"parsed": output}

        def destination(state):
            output = invoke("destination", "research", state, DestinationOutput)
            approved = {p.id: p for p in catalog.places}
            if any(approved.get(p.id) != p for p in [*output.candidates, *output.alternatives]):
                raise ValueError("Unapproved destination record")
            if len({p.id for p in output.candidates}) != len(output.candidates):
                raise ValueError("Duplicate candidate IDs")
            return {"destination": output, "evidence": catalog.evidence}

        def preliminary(state):
            output = invoke("logistics", "preliminary", state, LogisticsOutput)
            approved = {a.id: a for a in catalog.accommodation}
            if len(output.accommodation) > 1 or any(
                approved.get(a.id) != a for a in output.accommodation
            ):
                raise ValueError("Unapproved accommodation")
            if output.accommodation and (
                output.accommodation[0].area_id != self.base_id
                or (self.accommodation_id and output.accommodation[0].id != self.accommodation_id)
            ):
                raise ValueError("Preliminary logistics changed selected accommodation")
            return {"preliminary": output, "evidence": catalog.evidence}

        def planner(state):
            output = invoke("planner", "plan", state, OrchestratorOutput)
            available = {p.id for p in state["destination"].candidates}
            if output.request != request or not set(output.selected_ids).issubset(available):
                raise ValueError("Selection changed immutable request or invented a place")
            if (
                len(output.selected_ids) != len(set(output.selected_ids))
                or len(output.selected_ids) > 20
            ):
                raise ValueError("Invalid selected candidate IDs")
            return {"selected": output}

        def scheduler(state):
            output = invoke("scheduler", "schedule", state, LogisticsOutput)
            stays, _ = options(state)
            if output.accommodation != stays:
                raise ValueError("Logistics changed selected accommodation")
            return {"days": output.days}

        def costing(state):
            # Fixture budget proposals cannot replace the deterministic arithmetic.
            proposed = invoke("budget", "cost", state, BudgetOutput)
            stays, base = options(state)
            trusted = FixtureSpecialist("budget").execute(
                request,
                FixtureContext(
                    catalog=catalog,
                    base_id=base,
                    now=now,
                    stage="cost",
                    days=state["days"],
                    accommodation=stays,
                ),
            )
            if proposed.budget != trusted.budget:
                raise ValueError("Budget differs from deterministic calculation")
            return {"budget": trusted.budget, "budget_alternatives": proposed.alternatives}

        def review(state):
            nonlocal last_reviewed
            stays, base = options(state)
            findings = validate_plan(
                request,
                state["days"],
                state["budget"],
                catalog,
                base_id=base,
                accommodation=stays[0] if stays else None,
                now=now,
            )
            extra = invoke("reviewer", "review", {**state, "findings": findings}, ReviewOutput)
            findings += [f for f in extra.findings if f not in findings]
            updated = {**state, "findings": findings}
            last_reviewed = result_for(updated, "reviewed")
            events = [
                sink.emit(
                    "validation_finding",
                    "review",
                    state["revision"],
                    [f"review-r{state['revision']}-finding-{i}"],
                )
                for i, _ in enumerate(findings)
            ]
            return {"findings": findings, "events": events}

        def decide(state):
            signature = fingerprint(state["days"], state["budget"], state["findings"])
            reason, owners = decision(
                state["findings"],
                state["revision"],
                self.max_revisions,
                signature,
                state.get("history", []),
            )
            # A dropped known leg can be rebuilt; absent route evidence cannot.
            for finding in state["findings"]:
                if finding.rule_id == "ROUTE_MISSING" and len(finding.entity_ids) == 2:
                    origin, destination = finding.entity_ids
                    if origin != destination and not any(
                        r.origin_id == origin
                        and r.destination_id == destination
                        and r.feasibility_supported
                        for r in catalog.routes
                    ):
                        reason, owners = "unresolved_evidence_or_constraint", []
            return {
                "stop_reason": reason,
                "owners": owners,
                "history": [*state.get("history", []), signature],
            }

        def repair(state):
            revision = state["revision"] + 1
            updates = dict(state.get("repair", {}))
            events = [sink.emit("revision_started", "repair", revision)]
            for owner in state["owners"]:
                guard()
                events.append(sink.emit("agent_started", "repair-" + owner, revision))
                if owner == "budget":
                    # Every alternative includes fresh routing, costing and independent validation.
                    alternatives = []
                    offered = (
                        state.get("budget_alternatives", [])
                        if self.mode == "model"
                        else [a.id for a in catalog.accommodation]
                    )
                    for stay in catalog.accommodation:
                        if stay.id not in offered:
                            continue
                        guard()
                        candidate = plan_local(
                            request,
                            catalog,
                            registry=self.registry,
                            base_id=stay.area_id,
                            accommodation_id=stay.id,
                            now=now,
                        )
                        if candidate.status == "validated_estimate":
                            alternatives.append((candidate.budget.total_high, stay.id))
                    if alternatives:
                        updates["accommodation_id"] = min(alternatives)[1]
                elif owner in {"destination", "orchestrator"}:
                    from dubai_planner.services.candidate_selection import select_candidates

                    updates["candidate_ids"] = [
                        p.id for p in select_candidates(request, catalog, now=now)
                    ]
                elif owner not in {"logistics", "reviewer"}:
                    raise ValueError("Unsupported repair owner")
                # Destination/orchestrator repairs refilter at selection; logistics fully rebuilds.
            return {"repair": updates, "revision": revision, "events": events}

        def finish(state):
            return {"result": result_for(state, state.get("stop_reason", "needs_input"))}

        def wrap(name, function):
            def node(state):
                guard(count=True)
                revision = state.get("revision", 0)
                started = sink.emit("agent_started", name, revision)
                update = function(state)
                guard()
                revision = update.get("revision", revision)
                ready = sink.emit("artifact_ready", name, revision, [f"{name}-r{revision}"])
                update["events"] = merge_records(update.get("events", []), [started, ready])
                if revision and (
                    (name == "scheduler" and update.get("days") != state.get("days"))
                    or (name == "costing" and update.get("budget") != state.get("budget"))
                ):
                    update["events"].append(
                        sink.emit("plan_changed", name, revision, [f"{name}-r{revision}"])
                    )
                return update

            return node

        builder = StateGraph(GraphState)
        for name, function in {
            "parse": parse,
            "destination": destination,
            "preliminary": preliminary,
            "planner": planner,
            "scheduler": scheduler,
            "costing": costing,
            "review": review,
            "decide": decide,
            "repair": repair,
            "finish": finish,
        }.items():
            builder.add_node(name, wrap(name, function))
        builder.add_edge(START, "parse")
        builder.add_conditional_edges(
            "parse",
            lambda s: "finish" if s["parsed"].clarification_fields else "research",
            {"finish": "finish", "research": "research"},
        )
        builder.add_node("research", wrap("research", lambda s: {}))
        builder.add_edge("research", "destination")
        builder.add_edge("research", "preliminary")
        builder.add_edge(["destination", "preliminary"], "planner")
        for source, target in [
            ("planner", "scheduler"),
            ("scheduler", "costing"),
            ("costing", "review"),
            ("review", "decide"),
            ("repair", "planner"),
        ]:
            builder.add_edge(source, target)
        builder.add_conditional_edges(
            "decide", lambda s: "repair" if s["stop_reason"] == "repair" else "finish"
        )
        builder.add_edge("finish", END)
        sink.emit("run_started", "run")
        try:
            guard()
            if context.dataset_version != catalog.dataset_version:
                raise ValueError("Run dataset changed")
            catalog.check_policy(self.registry, "read")
            final = builder.compile().invoke(
                {"revision": 0, "events": [], "evidence": [], "history": []},
                config={"recursion_limit": self.recursion_limit},
            )
            guard()
            result = final["result"]
        except Exception as exc:
            reason = (
                str(exc)
                if isinstance(exc, RunStopped)
                else ("graph_limit" if isinstance(exc, GraphRecursionError) else "invalid_artifact")
            )
            result = (
                last_reviewed.model_copy(deep=True)
                if last_reviewed
                else PlanResult(
                    run_id=context.run_id,
                    graph_version=self.graph_version,
                    request=request,
                    status="failed",
                )
            )
            result.status = (
                "cancelled" if reason == "cancelled" else ("partial" if last_reviewed else "failed")
            )
            result.validation_complete = False
            result.metrics.update(
                stop_reason=reason, node_calls=calls, model_calls=0, travel_api_calls=0
            )
            from dubai_planner.services.llm_gateway import ModelFailure

            if isinstance(exc, ModelFailure):
                result.metrics["stop_reason"] = exc.code
                if exc.code == "cancelled":
                    result.status = "cancelled"
        result.metrics.update(self.model_metrics())
        result.agent_summaries = self.model_summaries()
        sink.emit("run_completed", "run", result.revisions)
        return PlanResult.model_validate(result.model_dump())
