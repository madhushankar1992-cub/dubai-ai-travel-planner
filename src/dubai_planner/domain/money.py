from datetime import date
from typing import Literal

from pydantic import Field, model_validator

from .base import Count, Identifier, Model, Money, PositiveCount
from .requests import Travelers

BillingUnit = Literal[
    "per_person",
    "per_person_meal",
    "per_vehicle_trip",
    "per_room_night",
    "per_room_stay",
    "whole_party_stay",
    "per_journey",
]


class StayQuoteScope(Model):
    check_in: date
    check_out: date
    rooms: PositiveCount
    travelers: Travelers

    @model_validator(mode="after")
    def ordered_dates(self):
        if self.check_out <= self.check_in:
            raise ValueError("Quote check-out must follow check-in")
        return self

    def matches(self, request):
        return (
            request.check_in == self.check_in
            and request.check_out == self.check_out
            and request.rooms == self.rooms
            and request.travelers == self.travelers
        )


class PriceEvidence(Model):
    id: Identifier
    entity_id: Identifier
    currency: Literal["AED"] = "AED"
    low: Money | None = None
    high: Money | None = None
    unit: BillingUnit
    status: Literal["known", "estimated", "unknown"]
    basis: Literal["bounded", "starting_from"] = "bounded"
    taxes_fees: Literal["included", "excluded", "unknown"] = "unknown"
    age_category: str | None = None
    quote_date: date | None = None
    stay_scope: StayQuoteScope | None = None
    requires_opt_in: bool = False
    applicable_from: date | None = None
    applicable_to: date | None = None
    evidence_ids: list[Identifier] = Field(min_length=1)
    reason: str

    @model_validator(mode="after")
    def amounts(self):
        if self.stay_scope and self.unit != "whole_party_stay":
            raise ValueError("Scoped stay quotes must use whole_party_stay totals")
        if (
            self.applicable_from
            and self.applicable_to
            and self.applicable_to < self.applicable_from
        ):
            raise ValueError("Invalid price validity dates")
        if self.status == "unknown":
            if self.low is not None or self.high is not None:
                raise ValueError("Unknown prices must use null bounds")
        elif self.basis == "starting_from":
            if self.low is None or self.high is not None:
                raise ValueError(
                    "Starting-from offers have a lower bound only; never a guaranteed upper bound"
                )
        elif self.low is None or self.high is None or self.low > self.high:
            raise ValueError("Known/estimated prices require ordered bounds")
        return self


class CostLine(Model):
    id: Identifier
    category: Literal["accommodation", "food", "transport", "activity", "fees", "other"]
    price: PriceEvidence
    quantity: Count | None
    inclusions: list[str] = Field(default_factory=list)
    coverage_ids: list[Identifier] = Field(default_factory=list)
    fees_resolved: bool = False
    expense_scope: str | None = None


class BudgetSummary(Model):
    known_subtotal: Money = "0"
    estimated_low: Money | None = None
    estimated_high: Money | None = None
    missing_required_costs: list[str] = Field(default_factory=list)
    contingency: Money | None = None
    contingency_low: Money | None = None
    total_low: Money | None = None
    total_high: Money | None = None
    cap: Money | None = None
    compliance: Literal["within_estimate", "over_budget", "at_risk", "unknown"] = "unknown"
    exclusions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def consistent(self):
        if (self.total_low is None) != (self.total_high is None):
            raise ValueError("Total bounds must both be provided or both absent")
        if self.total_low is not None and self.total_low > self.total_high:
            raise ValueError("Total range is reversed")
        if self.compliance != "unknown":
            if self.missing_required_costs or self.cap is None or self.total_low is None:
                raise ValueError("Incomplete costs/cap cannot establish budget compliance")
            expected = (
                "over_budget"
                if self.total_low > self.cap
                else "within_estimate"
                if self.total_high <= self.cap
                else "at_risk"
            )
            if self.compliance != expected:
                raise ValueError("Budget status contradicts total bounds and cap")
        return self
