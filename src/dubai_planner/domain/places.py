from datetime import date, datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .base import Identifier, Model, PositiveCount, utc

Quality = Literal["known", "estimated", "stale", "unavailable", "conflicting"]


class Evidence(Model):
    id: Identifier
    source_id: Identifier
    url: str | None = None
    local_record_id: str | None = None
    retrieved_at: datetime
    source_updated_at: datetime | None = None
    applicable_from: date | None = None
    applicable_to: date | None = None
    dataset_version: str
    quality: Quality
    attribution: str
    retention_policy_id: Identifier
    method: str
    max_age_days: PositiveCount = 30

    _utc = field_validator("retrieved_at", "source_updated_at")(lambda v: utc(v) if v else v)

    @model_validator(mode="after")
    def references(self):
        if not self.url and not self.local_record_id:
            raise ValueError("Evidence needs a URL or local record ID")
        if (
            self.applicable_from
            and self.applicable_to
            and self.applicable_from > self.applicable_to
        ):
            raise ValueError("Invalid evidence applicability dates")
        return self


class Coordinates(Model):
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    precision: Literal["entrance", "centroid", "approximate"] = "approximate"


class OpeningWindow(Model):
    """Reviewed recurring local window, valid only within the supplied date range."""

    weekday: int = Field(strict=True, ge=0, le=6)
    start_minute: int = Field(strict=True, ge=0, lt=1440)
    end_minute: int = Field(strict=True, gt=0, le=1440)
    valid_from: date
    valid_to: date
    evidence_ids: list[Identifier] = Field(min_length=1)
    estimated: bool = False

    @model_validator(mode="after")
    def ordered(self):
        if self.end_minute <= self.start_minute or self.valid_to < self.valid_from:
            raise ValueError("Invalid opening window")
        return self


class PlaceCandidate(Model):
    id: Identifier
    name: str
    category: Literal["attraction", "restaurant", "area"]
    area: str
    destination: str = "Dubai"
    coordinates: Coordinates | None = None
    interests: list[str] = Field(default_factory=list)
    visit_minutes_min: PositiveCount
    visit_minutes_max: PositiveCount
    accessibility: Literal["known", "unknown"] = "unknown"
    accessibility_features: list[str] = Field(default_factory=list)
    hours: str | None = None
    opening_windows: list[OpeningWindow] = Field(default_factory=list)
    crowd_guidance: str | None = None
    summary: str
    field_evidence: dict[str, list[Identifier]]

    @model_validator(mode="after")
    def ranges(self):
        if self.visit_minutes_min > self.visit_minutes_max:
            raise ValueError("Visit duration range is reversed")
        required = {"identity", "visit_duration"}
        if self.coordinates:
            required.add("coordinates")
        if self.hours:
            required.add("hours")
        if self.accessibility == "known":
            required.add("accessibility")
        if not required.issubset(self.field_evidence) or any(
            not v for v in self.field_evidence.values()
        ):
            raise ValueError("Factual fields require nonempty evidence references")
        return self


class AccommodationOption(Model):
    id: Identifier
    area_id: Identifier
    name: str
    max_occupancy: PositiveCount | None = None
    max_adults: PositiveCount | None = None
    max_children: int | None = Field(default=None, strict=True, ge=0)
    verified_child_age_bands: list[str] | None = None
    price_id: Identifier | None = None
    availability: Literal["unknown", "unavailable"] = "unknown"
    evidence_ids: list[Identifier] = Field(min_length=1)
    notes: str
