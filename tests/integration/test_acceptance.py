from pathlib import Path

import pytest

from dubai_planner.services.planner import plan_local
from dubai_planner.storage.repository import CatalogRepository, ImportRejected


@pytest.mark.parametrize("days,nights", [(1, 0), (7, 5)])
def test_duration_does_not_imply_nights(catalog, registry, request_model, now, days, nights):
    request_model.days = days
    request_model.nights = nights
    result = plan_local(request_model, catalog, registry=registry, now=now)
    assert len(result.days) == days
    assert result.request.confirmed_nights == nights
    assert result.status == "partial"


def test_base_change_recomputes(catalog, registry, request_model, now):
    original = plan_local(request_model, catalog, registry=registry, now=now)
    alternative = plan_local(
        request_model, catalog, registry=registry, base_id="area-deira", now=now
    )
    assert original.run_id != alternative.run_id
    assert original.days[0].base_assumption != alternative.days[0].base_assumption
    assert original.days[0].routes != alternative.days[0].routes
    assert original.budget != alternative.budget
    assert alternative.findings


def test_same_version_conflict_retains_previous(tmp_path, catalog, registry):
    source = tmp_path / "catalog.json"
    source.write_text(catalog.model_dump_json(), encoding="utf-8")
    repo = CatalogRepository(tmp_path / "catalog.sqlite", registry)
    repo.import_file(source, tmp_path / "reports")
    changed = catalog.model_copy(deep=True)
    changed.places[0].summary = "Different content must have a new version"
    source.write_text(changed.model_dump_json(), encoding="utf-8")
    with pytest.raises(ImportRejected):
        repo.import_file(source, tmp_path / "reports")
    assert repo.load() == catalog


def test_no_paid_provider_references():
    for file in (Path("docs/research.md"), Path("docs/architecture.md")):
        assert "google" not in file.read_text(encoding="utf-8").casefold()
    for file in Path("src").rglob("*.py"):
        assert "maps.googleapis.com" not in file.read_text(encoding="utf-8")


def test_expired_offer_and_unknown_fees(catalog, registry, request_model, now):
    request_model.arrival = "2026-12-05"
    request_model.departure = "2026-12-08"
    request_model.check_in = "2026-12-05"
    request_model.check_out = "2026-12-08"
    result = plan_local(
        request_model,
        catalog,
        registry=registry,
        base_id="area-dubai-marina",
        accommodation_id="rove-marina",
        now=now,
    )
    assert result.budget.compliance == "unknown"
    assert any(
        "quote" in reason or "inapplicable" in reason
        for reason in result.budget.missing_required_costs
    )
    assert result.status == "partial"
