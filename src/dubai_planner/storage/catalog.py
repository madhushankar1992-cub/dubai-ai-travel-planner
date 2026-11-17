from typing import Literal

from pydantic import Field, model_validator

from dubai_planner.domain.base import Identifier, Model
from dubai_planner.domain.itinerary import RouteLeg
from dubai_planner.domain.money import PriceEvidence
from dubai_planner.domain.places import AccommodationOption, Evidence, PlaceCandidate


class Tariff(Model):
    id: Identifier
    name: str
    conditions: str
    evidence_ids: list[Identifier] = Field(min_length=1)


class Catalog(Model):
    schema_version: Literal["1.0"] = "1.0"
    dataset_version: str = Field(min_length=1)
    evidence: list[Evidence]
    places: list[PlaceCandidate]
    accommodation: list[AccommodationOption]
    prices: list[PriceEvidence]
    routes: list[RouteLeg]
    tariffs: list[Tariff]

    @model_validator(mode="after")
    def references(self):
        all_records = [*self.places, *self.accommodation, *self.prices, *self.routes, *self.tariffs]
        ids = [r.id for r in all_records]
        if len(ids) != len(set(ids)) or len({e.id for e in self.evidence}) != len(self.evidence):
            raise ValueError("Duplicate record or evidence IDs")
        evidence = {e.id for e in self.evidence}
        places = {p.id for p in self.places}
        areas = {p.id for p in self.places if p.category == "area"}
        price_ids = {p.id for p in self.prices}
        entities = (
            places
            | {a.id for a in self.accommodation}
            | {t.id for t in self.tariffs}
            | {r.id for r in self.routes}
        )
        for e in self.evidence:
            if e.dataset_version != self.dataset_version:
                raise ValueError(f"Evidence version mismatch: {e.id}")
            if e.source_id != e.retention_policy_id:
                raise ValueError(f"Evidence policy mismatch: {e.id}")
        for record in all_records:
            refs = (
                [eid for group in record.field_evidence.values() for eid in group]
                if isinstance(record, PlaceCandidate)
                else record.evidence_ids
            )
            if not set(refs).issubset(evidence):
                raise ValueError(f"Dangling evidence reference: {record.id}")
        for p in self.prices:
            if p.entity_id not in entities:
                raise ValueError(f"Unknown price entity: {p.id}")
        for place in self.places:
            for window in place.opening_windows:
                if not set(window.evidence_ids).issubset(evidence):
                    raise ValueError(f"Dangling opening evidence: {place.id}")
        for a in self.accommodation:
            if a.area_id not in areas or (a.price_id and a.price_id not in price_ids):
                raise ValueError(f"Unknown accommodation area/price: {a.id}")
            if a.price_id and next(p for p in self.prices if p.id == a.price_id).entity_id != a.id:
                raise ValueError(f"Accommodation price belongs to another entity: {a.id}")
        for r in self.routes:
            if r.origin_id not in places or r.destination_id not in places:
                raise ValueError(f"Unknown route endpoint: {r.id}")
            if r.price_id and r.price_id not in price_ids:
                raise ValueError(f"Unknown route price: {r.id}")
            if r.price_id and next(p for p in self.prices if p.id == r.price_id).entity_id != r.id:
                raise ValueError(f"Route price belongs to another entity: {r.id}")
        return self

    def check_policy(self, registry, operation="persist"):
        evidence = {e.id: e for e in self.evidence}
        for e in self.evidence:
            registry.require(e.source_id, "evidence", operation)
        for p in self.places:
            for window in p.opening_windows:
                for ref in window.evidence_ids:
                    registry.require(evidence[ref].source_id, "hours", operation)
            for field, refs in p.field_evidence.items():
                for ref in refs:
                    registry.require(evidence[ref].source_id, field, operation)
        for field in ("accommodation", "prices", "routes", "tariffs"):
            for record in getattr(self, field):
                for ref in record.evidence_ids:
                    registry.require(evidence[ref].source_id, field, operation)
