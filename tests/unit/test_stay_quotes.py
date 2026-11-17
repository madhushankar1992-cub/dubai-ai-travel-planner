from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from dubai_planner.domain.money import CostLine, StayQuoteScope
from dubai_planner.domain.requests import Travelers, TripRequest
from dubai_planner.providers.local import LocalProvider
from dubai_planner.services.costing import calculate_budget, quantity_for
from dubai_planner.services.planner import build_cost_lines


def dated_request():
    return TripRequest.model_validate_json(Path("evaluation/phase2-request.json").read_text())


def test_quotes_are_distinct_whole_stay_products(catalog, now):
    request = dated_request()
    totals = []
    for suffix in ("flex", "nonrefund"):
        stay = next(a for a in catalog.accommodation if a.id == "rove-marina-quote-" + suffix)
        lines, missing = build_cost_lines(request, [], stay, catalog, now=now)
        budget = calculate_budget(lines, request, missing_required=missing)
        assert not missing
        assert lines[0].quantity == 1
        assert lines[0].price.taxes_fees == "included"
        totals.append(budget.known_subtotal)
    assert totals == [Decimal("1557"), Decimal("1535")]


@pytest.mark.parametrize(
    "change",
    [
        {"check_in": date(2026, 11, 21), "check_out": date(2026, 11, 24)},
        {"check_out": date(2026, 11, 24), "nights": 4},
        {"travelers": Travelers(adults=2)},
        {"travelers": Travelers(adults=1, child_age_bands=["6-12"])},
        {"rooms": 2, "travelers": Travelers(adults=2)},
        {"check_in": None, "check_out": None},
    ],
)
def test_quote_cannot_be_reused_for_a_different_stay(catalog, change):
    price = next(p for p in catalog.prices if p.entity_id == "rove-marina-quote-flex")
    request = dated_request().model_copy(update=change)
    assert quantity_for(price, request) is None
    # Even a caller supplying the old quantity directly cannot validate this quote.
    budget = calculate_budget(
        [CostLine(id="stay", category="accommodation", price=price, quantity=1)], request
    )
    assert budget.compliance == "unknown"
    assert budget.known_subtotal == 0


def test_quote_freshness_and_exact_checkin(catalog, now):
    for on_date in (None, date(2026, 11, 19), date(2026, 11, 21)):
        assert (
            LocalProvider(catalog, now=lambda: now)
            .get_price("rove-marina-quote-flex", on_date)
            .status
            == "unavailable"
        )
    assert (
        LocalProvider(catalog, now=lambda: now)
        .get_price("rove-marina-quote-flex", date(2026, 11, 20))
        .status
        == "ok"
    )
    assert (
        LocalProvider(catalog, now=lambda: now + timedelta(days=1))
        .get_price("rove-marina-quote-flex", date(2026, 11, 20))
        .status
        == "unavailable"
    )


def test_invalid_quote_scope_rejected():
    with pytest.raises(ValueError):
        StayQuoteScope(
            check_in=date(2026, 11, 20),
            check_out=date(2026, 11, 20),
            rooms=1,
            travelers=Travelers(),
        )
