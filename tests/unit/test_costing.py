from decimal import Decimal

import pytest

from dubai_planner.domain.money import CostLine, PriceEvidence
from dubai_planner.domain.requests import Travelers
from dubai_planner.services.costing import calculate_budget, display_money, fee_line, quantity_for


def price(identifier, amount="100", unit="per_person", **kwargs):
    values = dict(
        id=identifier,
        entity_id=identifier,
        unit=unit,
        low=amount,
        high=amount,
        status="known",
        taxes_fees="included",
        evidence_ids=["synthetic"],
        reason="SYNTHETIC test only, not a real price",
    )
    values.update(kwargs)
    return PriceEvidence(**values)


def test_architecture_1260_fixture(request_model):
    request_model.travelers = Travelers(adults=2)
    quotes = [
        price("hotel", "300", "per_room_night"),
        price("tickets"),
        price("taxi", "40", "per_vehicle_trip"),
    ]
    counts = [
        quantity_for(quotes[0], request_model),
        quantity_for(quotes[1], request_model),
        quantity_for(quotes[2], request_model, occurrences=4, vehicle_capacity=4),
    ]
    assert counts == [3, 2, 4]
    lines = [
        CostLine(id=q.id, category=c, price=q, quantity=n)
        for q, n, c in zip(quotes, counts, ["accommodation", "activity", "transport"])
    ]
    result = calculate_budget(lines, request_model, contingency_rate=Decimal(0))
    assert result.known_subtotal == result.total_high == Decimal("1260")
    assert display_money(result.total_high) == "1260.00"


@pytest.mark.parametrize(
    "unit,expected",
    [("per_room_night", 6), ("per_room_stay", 2), ("whole_party_stay", 1), ("per_person_meal", 3)],
)
def test_billing_units(request_model, unit, expected):
    request_model.travelers = Travelers(adults=3)
    request_model.rooms = 2
    assert quantity_for(price("p", unit=unit), request_model) == expected


def test_age_categories_and_vehicle_capacity(request_model):
    request_model.travelers = Travelers(adults=2, child_age_bands=["3-5", "6-12", "0-2"])
    assert quantity_for(price("p", age_category="3-12"), request_model) == 2
    assert quantity_for(price("p", age_category="0-2"), request_model) == 1
    assert quantity_for(price("p", age_category="unsupported"), request_model) is None
    assert quantity_for(price("p", unit="per_vehicle_trip"), request_model, vehicle_capacity=4) == 2
    assert quantity_for(price("p", unit="per_vehicle_trip"), request_model) is None


@pytest.mark.parametrize(
    "low,high,cap,state",
    [
        ("90", "100", "110", "within_estimate"),
        ("100", "110", "115", "at_risk"),
        ("100", "100", "100", "over_budget"),
    ],
)
def test_budget_boundaries(request_model, low, high, cap, state):
    request_model.budget = cap
    p = price("p", low, high=high, status="estimated")
    result = calculate_budget(
        [CostLine(id="l", category="food", price=p, quantity=1)], request_model
    )
    assert result.compliance == state


@pytest.mark.parametrize(
    "change",
    [
        {"taxes_fees": "unknown"},
        {"taxes_fees": "excluded"},
        {"basis": "starting_from", "high": None},
        {"low": None, "high": None, "status": "unknown"},
    ],
)
def test_missing_costs_prevent_success(request_model, change):
    result = calculate_budget(
        [CostLine(id="l", category="food", price=price("p", **change), quantity=1)], request_model
    )
    assert result.compliance == "unknown" and result.total_high is None


def test_fees_and_overlap(request_model):
    line = CostLine(id="stay", category="accommodation", price=price("p"), quantity=2)
    with pytest.raises(ValueError, match="inclusive"):
        fee_line(identifier="tax", base=line, rate=Decimal("0.05"), evidence_ids=["synthetic"])
    line.price.taxes_fees = "excluded"
    fee = fee_line(identifier="tax", base=line, rate=Decimal("0.05"), evidence_ids=["synthetic"])
    assert fee.price.low == Decimal("10")
    line.fees_resolved = True
    assert (
        calculate_budget([line, fee], request_model, contingency_rate=Decimal(0)).total_high == 210
    )
    line.coverage_ids = ["journey-1"]
    other = line.model_copy(deep=True)
    other.id = "pass"
    with pytest.raises(ValueError, match="double charge"):
        calculate_budget([line, other], request_model)


def test_per_person_budget(request_model):
    request_model.travelers = Travelers(adults=2)
    request_model.budget_scope = "per_person"
    assert calculate_budget([], request_model).cap == Decimal("10000")


def test_explicit_flight_exclusion(request_model):
    flight = CostLine(
        id="flight",
        category="other",
        price=price("flight", "500"),
        quantity=1,
        expense_scope="flights",
    )
    meal = CostLine(id="meal", category="food", price=price("meal", "20"), quantity=1)
    assert (
        calculate_budget([flight, meal], request_model, contingency_rate=Decimal(0)).total_high
        == 20
    )
