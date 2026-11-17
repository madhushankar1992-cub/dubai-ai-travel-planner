from datetime import date, datetime
from typing import Generic, Literal, Protocol, TypeVar

from pydantic import Field

from dubai_planner.domain.base import Model
from dubai_planner.domain.itinerary import RouteLeg
from dubai_planner.domain.money import PriceEvidence
from dubai_planner.domain.places import AccommodationOption, Evidence, PlaceCandidate

T = TypeVar("T")


class ProviderResult(Model, Generic[T]):
    status: Literal[
        "ok",
        "empty",
        "unsupported",
        "unauthorized",
        "rate_limited",
        "unavailable",
        "invalid_response",
    ]
    data: T | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    freshness: Literal["known", "estimated", "stale", "unavailable", "conflicting"] = "unavailable"
    latency_ms: float = Field(default=0, ge=0)
    quota_used: int = Field(default=0, ge=0)
    travel_api_cost: Literal["0"] = "0"
    retry: Literal["never", "transient", "after_reset"] = "never"
    dataset_version: str | None = None


class LocalDataProvider(Protocol):
    def search_places(
        self,
        query: str = "",
        *,
        category: str | None = None,
        area: str | None = None,
        interests: list[str] | None = None,
        limit: int = 20,
    ) -> ProviderResult[list[PlaceCandidate]]: ...
    def get_place_details(self, entity_id: str) -> ProviderResult[PlaceCandidate]: ...
    def get_price(
        self, entity_id: str, on_date: date | None = None
    ) -> ProviderResult[list[PriceEvidence]]: ...
    def search_accommodation(
        self, area_id: str | None = None
    ) -> ProviderResult[list[AccommodationOption]]: ...
    def route(
        self, origin_id: str, destination_id: str, mode: str, departure: datetime | None = None
    ) -> ProviderResult[RouteLeg]: ...
