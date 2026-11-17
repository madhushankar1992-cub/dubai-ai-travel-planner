from datetime import date, timedelta
from decimal import Decimal

from dubai_planner.domain.places import OpeningWindow
from dubai_planner.providers.local import LocalProvider
from dubai_planner.services.coverage import coverage_report
from dubai_planner.services.planner import build_cost_lines


def test_public_entry_is_explicitly_free(catalog, now):
    provider = LocalProvider(catalog, now=lambda: now)
    for entity in ("kite-beach", "al-seef"):
        result = provider.get_price(entity)
        assert result.status == "ok"
        assert len(result.data) == 1
        price = result.data[0]
        assert price.low == price.high == Decimal("0")
        assert price.taxes_fees == "included"
        assert price.age_category == "all"
        assert "excluded" in price.reason


def test_expired_and_undated_hotel_offer_is_not_ok(catalog, now):
    provider = LocalProvider(catalog, now=lambda: now)
    assert provider.get_price("rove-marina").status == "unavailable"
    assert provider.get_price("rove-marina", date(2026, 12, 1)).status == "unavailable"
    valid = provider.get_price("rove-marina", date(2026, 11, 20))
    assert valid.status == "ok"
    assert valid.data[0].high is None
    assert any("no upper bound" in w for w in valid.warnings)


def test_coverage_does_not_count_expired_bounded_quote(catalog, now):
    # Synthetic upgrade solely to test date handling, never saved to the seed.
    price = next(p for p in catalog.prices if p.entity_id == "rove-marina")
    price = price.model_copy(
        update={"basis": "bounded", "high": price.low, "taxes_fees": "included"}
    )
    catalog.prices = [price if p.id == price.id else p for p in catalog.prices]
    assert (
        "rove-marina"
        not in coverage_report(catalog, now=now, on_date=date(2026, 11, 20))["missing"][
            "bounded_accommodation_quotes"
        ]
    )
    for travel_date in (None, date(2026, 12, 1)):
        assert (
            "rove-marina"
            in coverage_report(catalog, now=now, on_date=travel_date)["missing"][
                "bounded_accommodation_quotes"
            ]
        )


def test_window_counts_require_matching_day_and_fresh_evidence(catalog, now):
    place = next(p for p in catalog.places if p.id == "dubai-frame")
    place.opening_windows = [
        OpeningWindow(
            weekday=6,
            start_minute=480,
            end_minute=1260,
            valid_from="2026-11-15",
            valid_to="2026-11-22",
            evidence_ids=["ev-frame"],
        )
    ]

    def count(travel_date, reviewed_now=now):
        return coverage_report(catalog, now=reviewed_now, on_date=travel_date)["summary"][
            "candidates_with_dated_windows"
        ]

    assert count(date(2026, 11, 15)) == 1
    assert count(None) == count(date(2026, 11, 16)) == count(date(2026, 11, 29)) == 0
    assert count(date(2026, 11, 15), now + timedelta(days=31)) == 0


def test_room_categories_and_published_hours_remain_precise(catalog):
    stays = {a.id: a for a in catalog.accommodation}
    assert stays["rove-jbr"].max_occupancy == 2
    assert stays["rove-jbr"].max_children == 0
    assert stays["rove-la-mer"].verified_child_age_bands == ["6-12"]
    mall = next(p for p in catalog.places if p.id == "dubai-mall")
    assert "Mon-Thu 10:00-23:00" in mall.hours
    assert all(w.estimated for w in mall.opening_windows)
    assert all("ev-phase2-assumptions" in w.evidence_ids for w in mall.opening_windows)


def test_hotel_offer_cannot_cover_stay_past_expiry(catalog, request_model, now):
    request_model.check_in = "2026-11-29"
    request_model.check_out = "2026-12-02"
    stay = next(a for a in catalog.accommodation if a.id == "rove-marina")
    _, missing = build_cost_lines(request_model, [], stay, catalog, now=now)
    assert "stay: quote does not cover the entire stay" in missing
