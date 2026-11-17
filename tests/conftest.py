from datetime import datetime, timezone
from pathlib import Path

import pytest

from dubai_planner.domain.requests import TripRequest
from dubai_planner.providers.policy import PolicyRegistry
from dubai_planner.storage.repository import read_catalog


@pytest.fixture
def now():
    return datetime(2026, 11, 15, 18, tzinfo=timezone.utc)


@pytest.fixture
def catalog():
    return read_catalog(Path("data/curated/dubai-seed.json"))


@pytest.fixture
def registry():
    return PolicyRegistry.load(Path("config/provider_policies/sources.json"))


@pytest.fixture
def request_model():
    return TripRequest(
        id="test-request",
        days=4,
        nights=3,
        budget="5000",
        budget_scope="total_trip",
        interests=["culture", "food", "beach"],
    )
