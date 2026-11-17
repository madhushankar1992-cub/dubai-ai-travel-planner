"""Unit-aware Decimal costing. No model output participates in arithmetic."""

from decimal import ROUND_HALF_UP, Decimal
from math import ceil

from dubai_planner.domain.money import BudgetSummary, CostLine, PriceEvidence


def display_money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def quantity_for(price: PriceEvidence, request, *, occurrences=1, vehicle_capacity=None):
    if type(occurrences) is not int or occurrences < 0:
        raise ValueError("Occurrences must be a nonnegative integer")
    unit = price.unit
    if price.stay_scope and not price.stay_scope.matches(request):
        return None
    if unit == "per_room_night":
        nights = request.confirmed_nights
        return None if nights is None else request.rooms * nights
    if unit == "per_room_stay":
        return request.rooms
    if unit == "whole_party_stay":
        return 1
    if unit == "per_vehicle_trip":
        if type(vehicle_capacity) is not int or vehicle_capacity <= 0:
            return None
        return ceil(request.travelers.total / vehicle_capacity) * occurrences
    age = price.age_category
    if age in (None, "all"):
        count = request.travelers.total
    elif age == "adult":
        count = request.travelers.adults
    elif age in {"0-2", "3-5", "6-12", "13-17"}:
        count = request.travelers.child_age_bands.count(age)
    elif age == "3-12":
        count = sum(a in {"3-5", "6-12"} for a in request.travelers.child_age_bands)
    else:
        return None  # A standard tariff does not establish child eligibility.
    return count * occurrences


def calculate_budget(
    lines: list[CostLine], request, *, contingency_rate=Decimal("0.10"), missing_required=()
) -> BudgetSummary:
    if (
        not isinstance(contingency_rate, Decimal)
        or not contingency_rate.is_finite()
        or contingency_rate < 0
    ):
        raise ValueError("Contingency must be a nonnegative finite Decimal")
    missing = list(missing_required)
    if len({line.id for line in lines}) != len(lines):
        raise ValueError("Duplicate cost line IDs")
    known = low = high = Decimal(0)
    covered = set()
    for line in lines:
        if line.expense_scope and line.expense_scope.casefold() in {
            e.casefold() for e in request.exclusions
        }:
            continue
        price = line.price
        if price.requires_opt_in and not request.accept_planning_estimates:
            missing.append(line.id + ": planning allowance requires explicit acceptance")
            continue
        if price.stay_scope and not price.stay_scope.matches(request):
            missing.append(line.id + ": quote does not match stay dates, rooms or travelers")
            continue
        if covered.intersection(line.coverage_ids):
            raise ValueError("Overlapping pass/ticket or fee coverage would double charge")
        covered.update(line.coverage_ids)
        if line.quantity == 0:
            continue
        if line.quantity is None or price.status == "unknown" or price.high is None:
            missing.append(line.id + ": unknown quantity or price bounds")
            continue
        if price.taxes_fees != "included" and not line.fees_resolved:
            missing.append(line.id + ": mandatory fees unresolved")
        lo, hi = price.low * line.quantity, price.high * line.quantity
        low += lo
        high += hi
        if price.status == "known" and lo == hi:
            known += lo
    cap = request.budget
    if request.budget_scope == "per_person" and cap is not None:
        cap *= request.travelers.total
    if request.budget_scope is None:
        cap = None
    complete = not missing
    total_low = low * (1 + contingency_rate) if complete else None
    total_high = high * (1 + contingency_rate) if complete else None
    state = "unknown"
    if complete and cap is not None:
        state = (
            "over_budget"
            if total_low > cap
            else "within_estimate"
            if total_high <= cap
            else "at_risk"
        )
    return BudgetSummary(
        known_subtotal=known,
        estimated_low=low,
        estimated_high=high,
        missing_required_costs=sorted(set(missing)),
        contingency=high * contingency_rate if complete else None,
        contingency_low=low * contingency_rate if complete else None,
        total_low=total_low,
        total_high=total_high,
        cap=cap,
        compliance=state,
        exclusions=request.exclusions,
    )


def fee_line(*, identifier, base: CostLine, rate: Decimal, evidence_ids: list[str]):
    """Apply an explicit source-defined percentage to this base only, once."""
    if base.price.taxes_fees == "included":
        raise ValueError("Cannot add fees to an inclusive quote")
    if not isinstance(rate, Decimal) or not rate.is_finite() or rate < 0:
        raise ValueError("Fee rate must be a nonnegative finite Decimal")
    usable = base.quantity is not None and base.price.high is not None
    price = PriceEvidence(
        id=identifier,
        entity_id=base.price.entity_id,
        unit="whole_party_stay",
        low=base.price.low * base.quantity * rate if usable else None,
        high=base.price.high * base.quantity * rate if usable else None,
        status="estimated" if usable else "unknown",
        taxes_fees="included",
        evidence_ids=evidence_ids,
        reason="Explicit rate applied to specified base",
    )
    return CostLine(
        id=identifier,
        category="fees",
        price=price,
        quantity=1,
        coverage_ids=[f"fee:{base.id}:{identifier}"],
    )
