"""Record-level inventory of usable evidence; counts never imply itinerary feasibility."""

from .evidence import evidence_index, price_usable, usable


def coverage_report(catalog, *, now=None, on_date=None):
    evidence = evidence_index(catalog)
    places = [p for p in catalog.places if p.category != "area"]
    rows = []
    for place in places:
        prices = [p for p in catalog.prices if p.entity_id == place.id]
        bounded = [
            p
            for p in prices
            if p.status != "unknown"
            and p.high is not None
            and price_usable(p, evidence, now=now, on_date=on_date)
        ]
        rows.append(
            {
                "id": place.id,
                "category": place.category,
                "coordinates": place.coordinates.precision if place.coordinates else "missing",
                "published_hours": bool(place.hours)
                and usable(place.field_evidence.get("hours", []), evidence, now=now),
                "dated_opening_windows": sum(
                    on_date is not None
                    and w.weekday == on_date.weekday()
                    and w.valid_from <= on_date <= w.valid_to
                    and usable(w.evidence_ids, evidence, now=now, on_date=on_date)
                    for w in place.opening_windows
                ),
                "bounded_price_records": len(bounded),
                "fee_inclusive_price_records": sum(p.taxes_fees == "included" for p in bounded),
                "accessibility_verified": place.accessibility == "known"
                and usable(place.field_evidence.get("accessibility", []), evidence, now=now),
            }
        )
    return {
        "dataset_version": catalog.dataset_version,
        "on_date": on_date.isoformat() if on_date else None,
        "scope": "Catalog inventory only; price product, party eligibility and travel-date checks still required.",
        "summary": {
            "places": len(catalog.places),
            "visit_candidates": len(places),
            "candidates_with_bounded_prices": sum(r["bounded_price_records"] > 0 for r in rows),
            "candidates_with_published_hours": sum(r["published_hours"] for r in rows),
            "candidates_with_dated_windows": sum(r["dated_opening_windows"] > 0 for r in rows),
            "accommodation_with_occupancy": sum(
                a.max_occupancy is not None and usable(a.evidence_ids, evidence, now=now)
                for a in catalog.accommodation
            ),
            "routes": len(catalog.routes),
            "routes_with_feasibility_evidence": sum(
                r.feasibility_supported and usable(r.evidence_ids, evidence, now=now)
                for r in catalog.routes
            ),
        },
        "places": rows,
        "missing": {
            "bounded_prices": [r["id"] for r in rows if not r["bounded_price_records"]],
            "published_hours": [r["id"] for r in rows if not r["published_hours"]],
            "dated_windows": [r["id"] for r in rows if not r["dated_opening_windows"]],
            "accommodation_occupancy": [
                a.id
                for a in catalog.accommodation
                if a.max_occupancy is None or not usable(a.evidence_ids, evidence, now=now)
            ],
            "bounded_accommodation_quotes": [
                a.id
                for a in catalog.accommodation
                if not any(
                    p.id == a.price_id
                    and p.high is not None
                    and p.taxes_fees == "included"
                    and p.status != "unknown"
                    and price_usable(p, evidence, now=now, on_date=on_date)
                    for p in catalog.prices
                )
            ],
        },
    }
