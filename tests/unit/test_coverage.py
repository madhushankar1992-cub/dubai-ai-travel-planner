from datetime import timedelta

from dubai_planner.domain.money import BudgetSummary
from dubai_planner.services.coverage import coverage_report
from dubai_planner.services.validation import validate_plan


def test_coverage_does_not_promote_heuristics(catalog, now):
    report = coverage_report(catalog, now=now)
    assert report["summary"]["routes_with_feasibility_evidence"] == 20
    assert all(not r.feasibility_supported for r in catalog.routes if r.id.startswith("route-"))
    assert report["summary"]["candidates_with_dated_windows"] == 0
    assert len(report["missing"]["bounded_accommodation_quotes"]) == len(catalog.accommodation)
    assert "shindagha" not in report["missing"]["bounded_prices"]
    assert "al-fahidi" in report["missing"]["bounded_prices"]


def test_coverage_expires(catalog, now):
    report = coverage_report(catalog, now=now + timedelta(days=366))
    assert report["summary"]["candidates_with_bounded_prices"] == 0
    assert report["summary"]["accommodation_with_occupancy"] == 0


def test_room_capacity_does_not_allow_three_adults(catalog, request_model, now):
    request_model.travelers.adults = 3
    stay = next(a for a in catalog.accommodation if a.id == "rove-marina")
    findings = validate_plan(
        request_model,
        [],
        BudgetSummary(),
        catalog,
        base_id=stay.area_id,
        accommodation=stay,
        now=now,
    )
    assert any(f.rule_id == "OCCUPANCY_EXCEEDED" for f in findings)


def test_room_child_band_crossing_age_limit_needs_confirmation(catalog, request_model, now):
    request_model.travelers.child_age_bands = ["13-17"]
    stay = next(a for a in catalog.accommodation if a.id == "rove-marina")
    findings = validate_plan(
        request_model,
        [],
        BudgetSummary(),
        catalog,
        base_id=stay.area_id,
        accommodation=stay,
        now=now,
    )
    assert any(f.rule_id == "OCCUPANCY_UNKNOWN" for f in findings)


def test_enriched_catalog_policy_and_products(catalog, registry):
    catalog.check_policy(registry, "export")
    prices = {p.entity_id: p for p in catalog.prices}
    assert str(prices["jumeirah-mosque"].low) == "55"
    assert prices["jumeirah-mosque"].taxes_fees == "unknown"
    assert prices["alfanar-barsha"].unit == "per_person_meal"
    mosque = next(p for p in catalog.places if p.id == "jumeirah-mosque")
    assert not mosque.opening_windows  # Fixed sessions must not become all-day admission.
