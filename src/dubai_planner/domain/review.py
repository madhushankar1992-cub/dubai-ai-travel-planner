from typing import Literal

from pydantic import Field, model_validator

from .base import Identifier, Model
from .itinerary import DayPlan
from .money import BudgetSummary
from .places import AccommodationOption, Evidence
from .requests import TripRequest

Outcome = Literal[
    "needs_input", "validated_estimate", "partial", "infeasible", "failed", "cancelled"
]
AgentRole = Literal["orchestrator", "destination", "logistics", "budget", "reviewer"]


class ReviewFinding(Model):
    rule_id: Identifier
    severity: Literal["error", "warning", "info"]
    entity_ids: list[Identifier] = Field(default_factory=list)
    evidence_ids: list[Identifier] = Field(default_factory=list)
    owner: AgentRole
    message: str
    proposed_action: str
    hard: bool = True


class RevisionRequest(Model):
    revision: int = Field(strict=True, ge=1, le=2)
    findings: list[ReviewFinding] = Field(min_length=1)
    allowed_edits: list[str]
    immutable_constraint_ids: list[Identifier]
    invalidated_artifacts: list[Identifier]


class PlanResult(Model):
    schema_version: Literal["1.0"] = "1.0"
    run_id: Identifier
    graph_version: str = "not-implemented"
    request: TripRequest
    status: Outcome
    days: list[DayPlan] = Field(default_factory=list)
    accommodation: list[AccommodationOption] = Field(default_factory=list)
    budget: BudgetSummary | None = None
    findings: list[ReviewFinding] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    agent_summaries: list[str] = Field(default_factory=list)
    sources: list[Evidence] = Field(default_factory=list)
    freshness_warnings: list[str] = Field(default_factory=list)
    revisions: int = Field(default=0, strict=True, ge=0, le=2)
    validation_complete: bool = False
    metrics: dict[str, int | str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def honest_status(self):
        if len({d.day for d in self.days}) != len(self.days):
            raise ValueError("Duplicate day numbers")
        if any(d.day > self.request.days for d in self.days):
            raise ValueError("Day exceeds request duration")
        if self.status == "validated_estimate":
            if self.request.clarification_fields() or not self.validation_complete:
                raise ValueError("Unresolved input or unfinished validation prevents success")
            if (
                len(self.days) != self.request.days
                or not self.budget
                or self.budget.compliance != "within_estimate"
            ):
                raise ValueError("Success requires every day and a complete within-estimate budget")
            if any(f.hard and f.severity == "error" for f in self.findings):
                raise ValueError("Hard errors prevent success")
        return self
