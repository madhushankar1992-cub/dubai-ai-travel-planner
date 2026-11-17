from datetime import date
from typing import Literal

from pydantic import Field, model_validator

from .base import Count, Identifier, Model, Money, PositiveCount


class Constraint(Model):
    id: Identifier
    field: str
    operator: Literal["eq", "ne", "le", "ge", "includes", "excludes"]
    value: str | int | bool | list[str]
    priority: Literal["hard", "soft"] = "hard"
    origin: Literal["user", "default", "derived"] = "user"


class Travelers(Model):
    adults: PositiveCount = 1
    child_age_bands: list[Literal["0-2", "3-5", "6-12", "13-17"]] = Field(default_factory=list)

    @property
    def total(self) -> int:
        return self.adults + len(self.child_age_bands)


class TripRequest(Model):
    id: Identifier
    schema_version: Literal["1.0"] = "1.0"
    destination: Literal["Dubai"] = "Dubai"
    days: int = Field(strict=True, ge=1, le=7)
    timezone: Literal["Asia/Dubai"] = "Asia/Dubai"
    arrival: date | None = None
    departure: date | None = None
    arrival_minute: int = Field(default=540, strict=True, ge=0, lt=1440)
    departure_minute: int = Field(default=1200, strict=True, gt=0, le=1440)
    check_in: date | None = None
    check_out: date | None = None
    travelers: Travelers = Field(default_factory=Travelers)
    rooms: PositiveCount = 1
    nights: Count | None = None
    budget: Money | None = None
    budget_scope: Literal["total_trip", "per_person"] | None = None
    interests: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=lambda: ["flights"])
    mobility_needs: list[str] = Field(default_factory=list)
    transport_preferences: list[str] = Field(default_factory=list)
    constraints: list[Constraint] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    candidate_ids: list[Identifier] = Field(default_factory=list)
    price_choices: dict[Identifier, Identifier] = Field(default_factory=dict)
    meal_allowance_price_id: Identifier | None = None
    accept_planning_estimates: bool = False

    @model_validator(mode="after")
    def dates_and_occupancy(self):
        if self.days == 1 and self.arrival_minute >= self.departure_minute:
            raise ValueError("Departure time must follow arrival time for a one-day trip")
        if self.arrival and self.departure:
            if self.departure < self.arrival:
                raise ValueError("Departure must not precede arrival")
            if (self.departure - self.arrival).days + 1 != self.days:
                raise ValueError("Inclusive arrival/departure dates must match itinerary days")
        if self.check_in and self.check_out:
            derived = (self.check_out - self.check_in).days
            if derived <= 0 or (self.nights is not None and self.nights != derived):
                raise ValueError("Check-out must follow check-in and match confirmed nights")
        if self.rooms > self.travelers.total:
            raise ValueError("Rooms exceed travelers; clarify occupancy")
        if len({c.id for c in self.constraints}) != len(self.constraints):
            raise ValueError("Constraint IDs must be unique")
        return self

    @property
    def confirmed_nights(self) -> int | None:
        if self.check_in and self.check_out:
            return (self.check_out - self.check_in).days
        return self.nights

    def clarification_fields(self) -> list[str]:
        fields = []
        if self.budget is None:
            fields.append("budget")
        if self.budget_scope is None:
            fields.append("budget_scope")
        if self.confirmed_nights is None:
            fields.append("nights")
        for start, end in (("arrival", "departure"), ("check_in", "check_out")):
            if bool(getattr(self, start)) != bool(getattr(self, end)):
                fields.append(end if getattr(self, start) else start)
        return fields
