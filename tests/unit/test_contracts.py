from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from dubai_planner.config import load_settings
from dubai_planner.domain.itinerary import DatedWindow
from dubai_planner.domain.money import PriceEvidence
from dubai_planner.domain.requests import TripRequest
from dubai_planner.domain.review import PlanResult
from dubai_planner.ui.validation_view import STATUS_LABELS


@pytest.mark.parametrize("days", [0, 8, True, "4", 1.5])
def test_invalid_duration(days):
    with pytest.raises(ValidationError):
        TripRequest(id="test", days=days)


@pytest.mark.parametrize("amount", [-1, 2.5, True, "NaN", "Infinity"])
def test_invalid_money(amount):
    with pytest.raises(ValidationError):
        TripRequest(id="test", days=1, budget=amount)


def test_nights_and_budget_clarification():
    r = TripRequest(id="test", days=4)
    assert r.clarification_fields() == ["budget", "budget_scope", "nights"]
    r = TripRequest(id="test", days=4, check_in="2026-11-05", check_out="2026-11-08")
    assert r.confirmed_nights == 3
    with pytest.raises(ValidationError):
        TripRequest(id="test", days=4, arrival="2026-11-05", departure="2026-11-06")


def test_unknown_price_roundtrip():
    price = PriceEvidence(
        id="price",
        entity_id="place",
        unit="per_person",
        status="unknown",
        evidence_ids=["ev"],
        reason="Unverified",
    )
    assert PriceEvidence.model_validate_json(price.model_dump_json()).low is None
    assert '"low":null' in price.model_dump_json()


def test_aware_travel_times():
    w = DatedWindow(
        start=datetime(2026, 11, 5, 8, tzinfo=timezone.utc),
        end=datetime(2026, 11, 5, 9, tzinfo=timezone.utc),
    )
    assert w.start.hour == 12 and str(w.start.tzinfo) == "Asia/Dubai"
    with pytest.raises(ValidationError):
        DatedWindow(start=datetime(2026, 11, 5, 8), end=datetime(2026, 11, 5, 9))


def test_all_statuses_and_success_guard(request_model):
    for status in STATUS_LABELS:
        if status != "validated_estimate":
            assert PlanResult(run_id="r", request=request_model, status=status).status == status
    with pytest.raises(ValidationError):
        PlanResult(run_id="r", request=request_model, status="validated_estimate")


def test_configuration():
    settings = load_settings({})
    assert settings.data_mode == "local-only"
    assert not settings.capabilities["external_travel_data"]
    with pytest.raises(ValueError, match="Invalid configuration") as exc:
        load_settings({"MAX_REVISIONS": "secret-token-value"})
    assert "secret-token-value" not in str(exc.value)
    with pytest.raises(ValueError):
        load_settings({"LLM_MODEL": "test"})
