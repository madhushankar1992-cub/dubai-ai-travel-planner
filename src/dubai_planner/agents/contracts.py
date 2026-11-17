"""Agent boundary contracts. Agent execution is implemented in Phase 5."""

from typing import Protocol

from pydantic import Field

from dubai_planner.domain.base import Model
from dubai_planner.domain.itinerary import DayPlan
from dubai_planner.domain.money import BudgetSummary
from dubai_planner.domain.places import AccommodationOption, PlaceCandidate
from dubai_planner.domain.requests import TripRequest
from dubai_planner.domain.review import ReviewFinding


class DestinationOutput(Model):
    candidates: list[PlaceCandidate]
    alternatives: list[PlaceCandidate] = Field(default_factory=list)


class LogisticsOutput(Model):
    accommodation: list[AccommodationOption]
    days: list[DayPlan] = Field(default_factory=list)


class BudgetOutput(Model):
    budget: BudgetSummary
    alternatives: list[str] = Field(default_factory=list)


class ReviewOutput(Model):
    findings: list[ReviewFinding]
    recommendation: str


class OrchestratorOutput(Model):
    request: TripRequest
    clarification_fields: list[str] = Field(default_factory=list)
    selected_ids: list[str] = Field(default_factory=list)


class Specialist(Protocol):
    def execute(self, request: TripRequest, context: Model) -> Model: ...
