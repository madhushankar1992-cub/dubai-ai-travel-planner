from datetime import datetime
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator, model_validator

from .base import Identifier, Model, PositiveCount


def dubai_time(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Travel timestamps must be timezone-aware")
    return value.astimezone(ZoneInfo("Asia/Dubai"))


class RelativeWindow(Model):
    kind: Literal["relative"] = "relative"
    day: int = Field(strict=True, ge=1, le=7)
    start_minute: int = Field(strict=True, ge=0, lt=1440)
    end_minute: int = Field(strict=True, gt=0, le=1440)

    @model_validator(mode="after")
    def ordered(self):
        if self.end_minute <= self.start_minute:
            raise ValueError("Activity end must follow start")
        return self


class DatedWindow(Model):
    kind: Literal["dated"] = "dated"
    start: datetime
    end: datetime
    _local = field_validator("start", "end")(dubai_time)

    @model_validator(mode="after")
    def ordered(self):
        if self.end <= self.start:
            raise ValueError("Activity end must follow start")
        return self


Window = Annotated[RelativeWindow | DatedWindow, Field(discriminator="kind")]


class RouteLeg(Model):
    id: Identifier
    origin_id: Identifier
    destination_id: Identifier
    mode: Literal["walk", "taxi", "transit", "abra"]
    duration_min: PositiveCount | None = None
    duration_max: PositiveCount | None = None
    departure: datetime | None = None
    method: str
    evidence_ids: list[Identifier] = Field(min_length=1)
    price_id: Identifier | None = None
    status: Literal["estimated", "known", "unknown"] = "estimated"
    feasibility_supported: bool = False
    includes_contingency: bool = False
    _local = field_validator("departure")(lambda v: dubai_time(v) if v else v)

    @model_validator(mode="after")
    def ordered(self):
        if self.origin_id == self.destination_id:
            raise ValueError("A connecting leg needs distinct endpoints")
        if self.status == "unknown":
            if self.duration_min is not None or self.duration_max is not None:
                raise ValueError("Unknown route times must be null")
        elif (
            self.duration_min is None
            or self.duration_max is None
            or self.duration_min > self.duration_max
        ):
            raise ValueError("Route estimates need ordered positive bounds")
        return self


class ActivitySlot(Model):
    id: Identifier
    place_id: Identifier
    window: Window
    participants: PositiveCount
    booking_required: bool | None = None
    hours_check: Literal["checked", "unknown", "conflicting"] = "unknown"
    evidence_ids: list[Identifier] = Field(min_length=1)


class BreakSlot(Model):
    kind: Literal["meal", "rest"]
    window: Window


class DayPlan(Model):
    day: int = Field(strict=True, ge=1, le=7)
    activities: list[ActivitySlot] = Field(default_factory=list)
    routes: list[RouteLeg] = Field(default_factory=list)
    breaks: list[BreakSlot] = Field(default_factory=list)
    meal_rest_notes: list[str] = Field(default_factory=list)
    base_assumption: str

    @model_validator(mode="after")
    def unique_slots(self):
        if len({a.id for a in self.activities}) != len(self.activities):
            raise ValueError("Duplicate activity IDs")
        if any(
            isinstance(a.window, RelativeWindow) and a.window.day != self.day
            for a in self.activities
        ):
            raise ValueError("Relative activity day differs from day plan")
        if len({a.window.kind for a in self.activities}) > 1:
            raise ValueError("Do not mix dated and relative windows")
        return self
