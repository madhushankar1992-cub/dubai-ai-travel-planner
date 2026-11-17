"""Deterministic Specialist implementations. Never represented as model reasoning."""

from datetime import datetime

from pydantic import Field

from dubai_planner.agents.contracts import (
    BudgetOutput,
    DestinationOutput,
    LogisticsOutput,
    OrchestratorOutput,
    ReviewOutput,
)
from dubai_planner.domain.base import Model
from dubai_planner.domain.itinerary import DayPlan
from dubai_planner.domain.money import BudgetSummary
from dubai_planner.domain.places import AccommodationOption, PlaceCandidate
from dubai_planner.domain.review import ReviewFinding
from dubai_planner.services.candidate_selection import select_candidates
from dubai_planner.services.costing import calculate_budget
from dubai_planner.services.planner import build_cost_lines
from dubai_planner.services.scheduling import build_schedule
from dubai_planner.storage.catalog import Catalog


class FixtureContext(Model):
    catalog: Catalog
    base_id: str
    accommodation_id: str | None = None
    now: datetime
    revision: int = 0
    stage: str
    candidates: list[PlaceCandidate] = Field(default_factory=list)
    accommodation: list[AccommodationOption] = Field(default_factory=list)
    days: list[DayPlan] = Field(default_factory=list)
    budget: BudgetSummary | None = None
    findings: list[ReviewFinding] = Field(default_factory=list)


class FixtureSpecialist:
    def __init__(self, role):
        self.role = role

    def execute(self, request, context: FixtureContext):
        if self.role == "destination":
            return DestinationOutput(
                candidates=select_candidates(request, context.catalog, now=context.now)
            )
        if self.role == "orchestrator":
            return OrchestratorOutput(
                request=request,
                clarification_fields=request.clarification_fields(),
                selected_ids=[p.id for p in context.candidates],
            )
        if self.role == "planner":
            return OrchestratorOutput(
                request=request,
                clarification_fields=[],
                selected_ids=[p.id for p in context.candidates],
            )
        if self.role == "logistics":
            if context.stage == "preliminary":
                stays = (
                    [a for a in context.catalog.accommodation if a.id == context.accommodation_id]
                    if context.accommodation_id
                    else [a for a in context.catalog.accommodation if a.area_id == context.base_id][
                        :1
                    ]
                )
                if context.accommodation_id and not stays:
                    raise ValueError("Unknown accommodation")
                if stays and stays[0].area_id != context.base_id:
                    raise ValueError("Accommodation base mismatch")
                return LogisticsOutput(accommodation=stays)
            return LogisticsOutput(
                accommodation=context.accommodation,
                days=build_schedule(
                    request,
                    context.candidates,
                    context.catalog,
                    base_id=context.base_id,
                    now=context.now,
                ),
            )
        if self.role == "scheduler":
            return LogisticsOutput(
                accommodation=context.accommodation,
                days=build_schedule(
                    request,
                    context.candidates,
                    context.catalog,
                    base_id=context.base_id,
                    now=context.now,
                ),
            )
        if self.role == "budget":
            lines, missing = build_cost_lines(
                request,
                context.days,
                context.accommodation[0] if context.accommodation else None,
                context.catalog,
                now=context.now,
            )
            return BudgetOutput(budget=calculate_budget(lines, request, missing_required=missing))
        if self.role == "reviewer":
            return ReviewOutput(
                findings=[],
                recommendation="Fixture review; deterministic findings remain authoritative.",
            )
        raise ValueError("Unknown fixture specialist")
