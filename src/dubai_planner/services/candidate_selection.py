"""Stable hard filtering followed by interest ranking and area grouping."""

from dubai_planner.domain.requests import TripRequest
from dubai_planner.storage.catalog import Catalog

from .evidence import evidence_index, usable


def excluded(place, request: TripRequest) -> bool:
    tokens = {
        place.id.casefold(),
        place.name.casefold(),
        place.area.casefold(),
        place.category.casefold(),
        *(tag.casefold() for tag in place.interests),
    }
    exclusions = {item.casefold() for item in request.exclusions}
    for constraint in request.constraints:
        if (
            constraint.priority == "hard"
            and constraint.operator in {"excludes", "ne"}
            and constraint.field in {"place", "place_id", "category", "area", "interests"}
        ):
            values = constraint.value if isinstance(constraint.value, list) else [constraint.value]
            exclusions.update(str(value).casefold() for value in values)
    return bool(tokens & exclusions)


def accessibility_supported(place, request, evidence, now=None, on_date=None):
    return (
        place.accessibility == "known"
        and set(request.mobility_needs).issubset(place.accessibility_features)
        and usable(
            place.field_evidence.get("accessibility", []), evidence, now=now, on_date=on_date
        )
    )


def select_candidates(request: TripRequest, catalog: Catalog, *, limit: int = 20, now=None):
    if type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError("Candidate limit must be an integer from 1 to 20")
    evidence = evidence_index(catalog)
    rows = []
    for place in catalog.places:
        if (
            place.category == "area"
            or (request.candidate_ids and place.id not in request.candidate_ids)
            or place.destination != request.destination
            or excluded(place, request)
        ):
            continue
        if not usable(
            place.field_evidence.get("identity", []), evidence, now=now, on_date=request.arrival
        ):
            continue
        if request.mobility_needs and not accessibility_supported(
            place, request, evidence, now, request.arrival
        ):
            continue
        rows.append(place)
    interests = {i.casefold() for i in request.interests}
    rows.sort(key=lambda p: (-len(interests & {i.casefold() for i in p.interests}), p.area, p.id))
    return rows[:limit]


def cluster_candidates(candidates):
    groups = {}
    for place in candidates:
        groups.setdefault(place.area, []).append(place)
    return groups
