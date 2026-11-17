"""Evidence eligibility shared by selection, scheduling, costing and review."""

from datetime import date, datetime, timezone

from dubai_planner.domain.places import Evidence


def usable(
    refs: list[str],
    evidence: dict[str, Evidence],
    *,
    on_date: date | None = None,
    now: datetime | None = None,
) -> bool:
    now = now or datetime.now(timezone.utc)
    if not refs:
        return False
    for ref in refs:
        item = evidence.get(ref)
        if item is None or item.quality not in {"known", "estimated"}:
            return False
        age = (now - item.retrieved_at).total_seconds()
        if age < 0 or age > item.max_age_days * 86400:
            return False
        if on_date and (
            (item.applicable_from and on_date < item.applicable_from)
            or (item.applicable_to and on_date > item.applicable_to)
        ):
            return False
        if on_date is None and (item.applicable_from or item.applicable_to):
            return False
    return True


def evidence_index(catalog):
    return {item.id: item for item in catalog.evidence}


def price_usable(price, evidence, *, on_date=None, now=None):
    """Check the product's own dates as well as its source's review freshness."""
    if price.status == "unknown":
        return False
    if price.stay_scope and on_date != price.stay_scope.check_in:
        return False
    if price.applicable_from or price.applicable_to:
        if on_date is None:
            return False
        if price.applicable_from and on_date < price.applicable_from:
            return False
        if price.applicable_to and on_date > price.applicable_to:
            return False
    return usable(price.evidence_ids, evidence, on_date=on_date, now=now)
