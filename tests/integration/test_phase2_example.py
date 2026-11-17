import socket
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from dubai_planner.domain.requests import TripRequest
from dubai_planner.services.planner import plan_local


def example(catalog, registry, now, *, request=None, suffix="flex"):
    request = request or TripRequest.model_validate_json(
        Path("evaluation/phase2-request.json").read_text()
    )
    return plan_local(
        request,
        catalog,
        registry=registry,
        now=now,
        base_id="area-dubai-marina",
        accommodation_id="rove-marina-quote-" + suffix,
    )


def test_four_day_example_and_real_alternative_work_offline(catalog, registry, now, monkeypatch):
    def deny_network(*args, **kwargs):
        raise AssertionError("Phase 2 must not need network access")

    monkeypatch.setattr(socket.socket, "connect", deny_network)
    primary = example(catalog, registry, now)
    alternate = example(catalog, registry, now, suffix="nonrefund")
    for result in (primary, alternate):
        assert result.status == "validated_estimate"
        assert result.validation_complete
        assert not result.findings
        assert len(result.days) == 4
        assert all(day.activities and len(day.routes) == 2 for day in result.days)
        assert result.budget.total_high < result.budget.cap
        assert not result.budget.missing_required_costs
    assert primary.budget.total_high - alternate.budget.total_high == Decimal("24.20")


def test_estimates_are_opt_in_and_quote_staleness_blocks(catalog, registry, now):
    request = TripRequest.model_validate_json(Path("evaluation/phase2-request.json").read_text())
    request.accept_planning_estimates = False
    strict = example(catalog, registry, now, request=request)
    assert strict.status == "partial"
    assert any(f.rule_id == "HOURS_UNKNOWN" for f in strict.findings)
    assert strict.budget.compliance == "unknown"
    assert example(catalog, registry, now + timedelta(days=1)).status == "partial"


def test_missing_route_or_meal_cannot_validate(catalog, registry, now):
    removed = {
        r.id
        for r in catalog.routes
        if r.origin_id == "area-dubai-marina" and r.destination_id == "al-seef"
    }
    payload = catalog.model_dump()
    payload["prices"] = [p for p in payload["prices"] if p["entity_id"] not in removed]
    payload["routes"] = [r for r in payload["routes"] if r["id"] not in removed]
    catalog = type(catalog).model_validate(payload)
    result = example(catalog, registry, now)
    assert result.status == "partial"
    assert any(f.rule_id == "ROUTE_MISSING" for f in result.findings)
    request = TripRequest.model_validate_json(Path("evaluation/phase2-request.json").read_text())
    request.meal_allowance_price_id = None
    result = example(catalog, registry, now, request=request)
    assert any("remaining meals" in gap for gap in result.budget.missing_required_costs)
