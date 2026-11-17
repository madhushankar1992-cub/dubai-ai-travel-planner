"""Seeded randomized invariants for planning and graph orchestration."""

import random
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from dubai_planner.config import Settings
from dubai_planner.domain.requests import Travelers, TripRequest
from dubai_planner.services.planner import plan_local
from dubai_planner.services.run_service import run_fixture

BASE_REQUEST = TripRequest.model_validate_json(
    Path("evaluation/phase2-request.json").read_text(encoding="utf-8")
)
INTERESTS = ["culture", "food", "architecture", "shopping", "beach"]
STATUSES = {"validated", "validated_estimate", "partial", "needs_input", "failed"}


def randomized_request(seed):
    rng = random.Random(seed)
    days = rng.randint(1, 7)
    nights = rng.randint(1, max(1, days))
    adults = rng.randint(1, 4)
    candidate_count = rng.randint(1, len(BASE_REQUEST.candidate_ids))
    arrival = BASE_REQUEST.arrival
    return BASE_REQUEST.model_copy(
        deep=True,
        update={
            "id": f"random-{seed}",
            "days": days,
            "departure": arrival + timedelta(days=days - 1),
            "check_out": arrival + timedelta(days=nights),
            "nights": nights,
            "travelers": Travelers(adults=adults),
            "rooms": rng.randint(1, adults),
            "budget": Decimal(rng.randrange(1_500, 12_001, 50)),
            "interests": rng.sample(INTERESTS, rng.randint(1, len(INTERESTS))),
            "candidate_ids": rng.sample(BASE_REQUEST.candidate_ids, candidate_count),
        },
    )


@pytest.mark.parametrize("seed", range(40))
def test_randomized_deterministic_plans_preserve_core_invariants(seed, catalog, registry, now):
    request = randomized_request(seed)
    result = plan_local(
        request,
        catalog,
        registry=registry,
        base_id="area-dubai-marina",
        accommodation_id="rove-marina-quote-flex",
        now=now,
    )
    assert result.request == request
    assert result.status in STATUSES
    assert result.validation_complete
    assert result.budget is not None
    assert result.budget.cap == request.budget
    assert len(result.days) <= request.days
    assert all(1 <= day.day <= request.days for day in result.days)
    assert all(
        activity.place_id in set(request.candidate_ids)
        for day in result.days
        for activity in day.activities
    )


@pytest.mark.parametrize("seed", range(12))
def test_randomized_fixture_graph_terminates_with_bounded_execution(seed, catalog, registry, now):
    result = run_fixture(
        randomized_request(seed + 100),
        catalog,
        registry,
        settings=Settings(max_revisions=seed % 3),
        base_id="area-dubai-marina",
        accommodation_id="rove-marina-quote-flex",
        evidence_now=now,
    )
    assert result.status in STATUSES | {"cancelled"}
    assert result.graph_version == "fixture-langgraph-v2"
    assert 0 < result.metrics["node_calls"] <= 40
    assert result.metrics["model_calls"] == 0
