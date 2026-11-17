"""Models select grounded IDs; Python services retain facts, schedules and arithmetic."""

from threading import Lock
from typing import Literal

from pydantic import Field

from dubai_planner.agents.contracts import (
    BudgetOutput,
    DestinationOutput,
    LogisticsOutput,
    OrchestratorOutput,
    ReviewOutput,
)
from dubai_planner.agents.prompts import PROMPTS
from dubai_planner.domain.base import Identifier, Model
from dubai_planner.domain.requests import TripRequest
from dubai_planner.domain.review import ReviewFinding
from dubai_planner.services.candidate_selection import select_candidates
from dubai_planner.services.costing import calculate_budget
from dubai_planner.services.planner import build_cost_lines
from dubai_planner.services.scheduling import build_schedule


class Selection(Model):
    selected_ids: list[Identifier] = Field(max_length=20)
    evidence_ids: list[Identifier] = Field(max_length=80)
    summary: str = Field(min_length=1, max_length=500)


class Orchestration(Selection):
    clarification_fields: list[str]


class AccommodationChoice(Model):
    accommodation_id: Identifier | None
    evidence_ids: list[Identifier] = Field(max_length=80)
    summary: str = Field(min_length=1, max_length=500)


class BudgetAdvice(Model):
    alternative_accommodation_ids: list[Identifier] = Field(max_length=11)
    summary: str = Field(min_length=1, max_length=300)


class Observation(Model):
    kind: Literal["preference_fit", "evidence_gap"]
    entity_ids: list[Identifier] = Field(min_length=1, max_length=20)
    evidence_ids: list[Identifier] = Field(min_length=1, max_length=30)
    message: str = Field(min_length=1, max_length=300)


class ReviewAdvice(Model):
    observations: list[Observation] = Field(max_length=8)
    summary: str = Field(min_length=1, max_length=500)


class ExtractedRequest(Model):
    request: TripRequest | None
    clarification_fields: list[str]
    summary: str = Field(min_length=1, max_length=500)


def refs(record):
    if hasattr(record, "field_evidence"):
        return {ref for group in record.field_evidence.values() for ref in group}
    return set(record.evidence_ids)


def compact(record):
    values = record.model_dump(mode="json")
    keys = (
        "id",
        "name",
        "category",
        "area",
        "area_id",
        "interests",
        "hours",
        "price_id",
        "max_occupancy",
        "notes",
        "accessibility",
        "visit_minutes_min",
        "visit_minutes_max",
    )
    return {**{k: values[k] for k in keys if k in values}, "evidence_ids": sorted(refs(record))}


def cited(ids, evidence_ids, records):
    by_id = {record.id: record for record in records}
    if len(set(ids)) != len(ids) or not set(ids).issubset(by_id):
        raise ValueError("Unapproved or duplicate IDs")
    allowed = set().union(*(refs(r) for r in records)) if records else set()
    if not set(evidence_ids).issubset(allowed):
        raise ValueError("Unapproved evidence IDs")
    if any(not refs(by_id[key]).intersection(evidence_ids) for key in ids):
        raise ValueError("Selected record lacks supporting citation")
    return [by_id[key] for key in ids]


class ModelSpecialist:
    def __init__(self, role, gateway):
        self.role, self.gateway = role, gateway
        self.summaries = []
        self.lock = Lock()

    def execute(self, request, context):
        catalog = context.catalog
        data = {
            "task": context.stage,
            "revision": context.revision,
            "request": request.model_dump(mode="json"),
            "findings": [f.model_dump(mode="json") for f in context.findings],
        }

        def ask(schema, validate):
            data["evidence_as_of"] = context.now.isoformat()
            output = self.gateway.generate(
                self.role, PROMPTS[self.role], data, schema, validate=validate
            )
            with self.lock:
                self.summaries.append(
                    f"{self.role}/{context.stage}/r{context.revision}: {output.summary}"
                )
            return output

        if self.role == "orchestrator":
            required = request.clarification_fields()
            data.update(
                required_clarifications=required,
            )

            def validate(output):
                # Python owns both authoritative fields (see the return below): the
                # clarification list is the computed one and nothing is selected before
                # research. Only the schema and the model's summary are taken from the
                # reply, so a differently-worded echo must not fail the whole run.
                return output

            output = ask(Orchestration, validate)
            return OrchestratorOutput(
                request=request, clarification_fields=required, selected_ids=[]
            )
        if self.role == "planner":
            data["candidates"] = [compact(p) for p in context.candidates]

            def validate(output):
                if output.clarification_fields:
                    raise ValueError("Planner cannot introduce new clarification fields")
                cited(output.selected_ids, output.evidence_ids, context.candidates)
                if context.candidates and not output.selected_ids:
                    raise ValueError("Select supported candidates")
                return output

            output = ask(Orchestration, validate)
            return OrchestratorOutput(
                request=request, clarification_fields=[], selected_ids=output.selected_ids
            )
        if self.role == "destination":
            candidates = select_candidates(request, catalog, now=context.now)
            data["candidates"] = [compact(p) for p in candidates]

            def validate(output):
                cited(output.selected_ids, output.evidence_ids, candidates)
                if candidates and not output.selected_ids:
                    raise ValueError("Return supported candidates")
                return output

            output = ask(Selection, validate)
            return DestinationOutput(
                candidates=cited(output.selected_ids, output.evidence_ids, candidates)
            )
        if self.role == "logistics" and context.stage == "preliminary":
            stays = [
                a
                for a in catalog.accommodation
                if (
                    a.id == context.accommodation_id
                    if context.accommodation_id
                    else a.area_id == context.base_id
                )
            ]
            data["accommodation"] = [compact(a) for a in stays]

            def validate(output):
                if stays and not output.accommodation_id:
                    raise ValueError("Select allowed accommodation")
                cited(
                    [output.accommodation_id] if output.accommodation_id else [],
                    output.evidence_ids,
                    stays,
                )
                return output

            output = ask(AccommodationChoice, validate)
            return LogisticsOutput(
                accommodation=cited(
                    [output.accommodation_id] if output.accommodation_id else [],
                    output.evidence_ids,
                    stays,
                )
            )
        if self.role == "scheduler":
            data["candidates"] = [compact(p) for p in context.candidates]
            selected = {p.id for p in context.candidates} | {context.base_id}
            data["routes"] = [
                {
                    "origin": r.origin_id,
                    "destination": r.destination_id,
                    "mode": r.mode,
                    "minutes_max": r.duration_max,
                    "supported": r.feasibility_supported,
                }
                for r in catalog.routes
                if r.origin_id in selected and r.destination_id in selected
            ]

            def validate(output):
                cited(output.selected_ids, output.evidence_ids, context.candidates)
                if set(output.selected_ids) != {p.id for p in context.candidates}:
                    raise ValueError("Ordering must preserve selected candidates")
                return output

            output = ask(Selection, validate)
            ordered = cited(output.selected_ids, output.evidence_ids, context.candidates)
            return LogisticsOutput(
                accommodation=context.accommodation,
                days=build_schedule(
                    request, ordered, catalog, base_id=context.base_id, now=context.now
                ),
            )
        if self.role == "budget":
            lines, missing = build_cost_lines(
                request,
                context.days,
                context.accommodation[0] if context.accommodation else None,
                catalog,
                now=context.now,
            )
            budget = calculate_budget(lines, request, missing_required=missing)
            data["budget"] = budget.model_dump(mode="json", exclude={"lines"})
            alternative_required = budget.compliance in {"over_budget", "at_risk"}
            data["alternative_required"] = alternative_required
            # Hotel records are only useful when an alternative must be ranked. Omitting
            # them otherwise keeps the request small enough to stay inside Groq's
            # per-minute token limits (a 429 here previously stalled the whole run).
            if alternative_required:
                data["accommodation"] = [compact(a) for a in catalog.accommodation]
                stay_ids = {a.id for a in catalog.accommodation}
                data["accommodation_prices"] = [
                    p.model_dump(mode="json") for p in catalog.prices if p.entity_id in stay_ids
                ]
            else:
                data["accommodation"] = []
                data["accommodation_prices"] = []

            def validate(output):
                if not alternative_required and (output.alternative_accommodation_ids):
                    raise ValueError("Alternatives are not needed for a within-cap estimate")
                allowed = {stay.id for stay in catalog.accommodation}
                proposed = output.alternative_accommodation_ids
                if len(proposed) != len(set(proposed)) or not set(proposed).issubset(allowed):
                    raise ValueError("Budget proposed an unapproved or duplicate accommodation")
                return output

            output = ask(BudgetAdvice, validate)
            return BudgetOutput(budget=budget, alternatives=output.alternative_accommodation_ids)
        if self.role == "reviewer":
            selected_ids = {a.place_id for d in context.days for a in d.activities}
            records = [p for p in catalog.places if p.id in selected_ids] + context.accommodation
            data["records"] = [compact(r) for r in records]
            data["schedule"] = [
                {
                    "day": d.day,
                    "activities": [a.model_dump(mode="json") for a in d.activities],
                    "route_ids": [r.id for r in d.routes],
                }
                for d in context.days
            ]
            data["budget"] = (
                context.budget.model_dump(mode="json", exclude={"lines"})
                if context.budget
                else None
            )

            def validate(output):
                for issue in output.observations:
                    cited(issue.entity_ids, issue.evidence_ids, records)
                return output

            output = ask(ReviewAdvice, validate)
            return ReviewOutput(
                findings=[
                    ReviewFinding(
                        rule_id="MODEL_" + issue.kind.upper(),
                        severity="warning",
                        hard=False,
                        entity_ids=issue.entity_ids,
                        evidence_ids=issue.evidence_ids,
                        owner="reviewer",
                        message=issue.message,
                        proposed_action="Review the cited limitation before travel.",
                    )
                    for issue in output.observations
                ],
                recommendation=output.summary,
            )
        raise ValueError("Unknown model specialist")


def extract_request(text, gateway):
    if not text.strip() or len(text.encode()) > 10_000:
        raise ValueError("Request text must contain 1–10000 bytes")

    def validate(output):
        expected = output.request.clarification_fields() if output.request else ["days"]
        if output.clarification_fields != expected:
            raise ValueError("Missing-input fields do not match proposed request")
        return output

    return gateway.generate(
        "orchestrator", PROMPTS["extract"], {"user_text": text}, ExtractedRequest, validate=validate
    )
