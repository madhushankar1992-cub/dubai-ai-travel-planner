import json
from pathlib import Path
from time import sleep

import pytest

from dubai_planner.domain.requests import TripRequest
from dubai_planner.providers.policy import PolicyDenied
from dubai_planner.services.catalog_editor import edited_catalog
from dubai_planner.services.planner import plan_local
from dubai_planner.storage.plans import PlanRepository
from dubai_planner.storage.repository import CatalogRepository, ImportRejected


def test_edit_preserves_review_dates_and_rejects_conflicts(catalog, registry, tmp_path):
    repo = CatalogRepository(tmp_path / "data.sqlite", registry)
    repo.import_json(catalog.model_dump_json(), tmp_path / "reports")
    record = catalog.places[0].model_dump(mode="json")
    record["summary"] = "Reviewed local description"
    updated = edited_catalog(catalog, "places", json.dumps(record), original_id=record["id"])
    assert updated.dataset_version != catalog.dataset_version
    assert [e.retrieved_at for e in updated.evidence] == [e.retrieved_at for e in catalog.evidence]
    repo.import_json(
        updated.model_dump_json(), tmp_path / "reports", expected_version=catalog.dataset_version
    )
    with pytest.raises(ImportRejected):
        repo.import_json(
            catalog.model_dump_json(),
            tmp_path / "reports",
            expected_version=catalog.dataset_version,
        )
    assert repo.load() == updated
    with pytest.raises(ValueError):
        edited_catalog(catalog, "places", json.dumps(record))
    record["field_evidence"]["identity"] = ["missing-source"]
    with pytest.raises(ValueError):
        edited_catalog(catalog, "places", json.dumps(record), original_id=record["id"])


def test_saved_plans_roundtrip_deduplicate_and_recheck_policy(catalog, registry, now, tmp_path):
    request = TripRequest.model_validate_json(Path("evaluation/phase2-request.json").read_text())
    result = plan_local(
        request,
        catalog,
        registry=registry,
        base_id="area-dubai-marina",
        accommodation_id="rove-marina-quote-flex",
        now=now,
    )
    store = PlanRepository(tmp_path / "plans.sqlite", registry)
    assert store.list() == []
    identifier = store.save(result, "My Dubai trip")
    assert store.save(result, "My Dubai trip") == identifier
    assert len(store.list()) == 1
    assert store.load(identifier) == result
    assert json.loads(store.export(result))["status"] == "validated_estimate"
    assert store.database.stat().st_size < 100_000
    registry.policies[result.sources[0].source_id].approved = False
    with pytest.raises(PolicyDenied):
        store.load(identifier)
    with pytest.raises(PolicyDenied):
        store.save(result, "Revoked")


def test_bad_json_does_not_replace_catalog(catalog, registry, tmp_path):
    repo = CatalogRepository(tmp_path / "data.sqlite", registry)
    repo.import_json(catalog.model_dump_json(), tmp_path / "reports")
    with pytest.raises(ImportRejected):
        repo.import_json('{"places": []}', tmp_path / "reports")
    assert repo.load() == catalog


def test_workspace_bootstraps_bundled_catalog_on_fresh_start(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest

    database = tmp_path / "fresh-cloud-workspace.sqlite"
    monkeypatch.setenv("DATABASE_PATH", str(database))
    app = AppTest.from_file(Path("app.py").resolve(), default_timeout=15).run()
    assert not app.exception
    assert database.exists()
    assert app.sidebar.radio[0].value == "Plan a trip"


def test_workspace_generate_save_reopen(catalog, registry, tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest

    database = tmp_path / "workspace.sqlite"
    CatalogRepository(database, registry).import_json(
        catalog.model_dump_json(), tmp_path / "reports"
    )
    monkeypatch.setenv("DATABASE_PATH", str(database))
    app = AppTest.from_file(Path("app.py").resolve(), default_timeout=15).run()
    assert not app.exception
    app.sidebar.radio[0].set_value("Manage travel data").run()
    assert not app.exception
    app.sidebar.radio[0].set_value("Plan a trip").run()
    app.checkbox[0].check()
    next(b for b in app.button if b.label == "Create my itinerary").click().run()
    assert not app.exception
    assert app.session_state["planner_result"]
    next(b for b in app.button if b.label == "Save itinerary").click().run()
    assert not app.exception
    assert len(PlanRepository(database, registry).list()) == 1
    reopened = AppTest.from_file(Path("app.py").resolve(), default_timeout=15).run()
    reopened.sidebar.radio[0].set_value("Saved itineraries").run()
    assert not reopened.exception
    assert reopened.selectbox[0].value
    next(b for b in reopened.button if b.label == "Recheck with current data").click().run()
    assert not reopened.exception
    assert reopened.session_state["planner_result"]


def test_agent_workspace_runs_graph_once_across_rerenders(catalog, registry, tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest

    database = tmp_path / "agent-workspace.sqlite"
    CatalogRepository(database, registry).import_json(
        catalog.model_dump_json(), tmp_path / "agent-reports"
    )
    monkeypatch.setenv("DATABASE_PATH", str(database))
    # The UI must retain a complete local fixture path without model credentials.
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    app = AppTest.from_file(Path("app.py").resolve(), default_timeout=15).run()
    app.sidebar.radio[0].set_value("Agent planner").run()
    assert not app.exception
    assert app.radio[0].value == "Fixture graph"
    next(box for box in app.checkbox if "planning allowances" in box.label).check()
    next(button for button in app.button if button.label == "Start agent planning").click().run()
    run_id = app.session_state["agent_run_registry"].active_id
    for _ in range(100):
        snapshot = app.session_state["agent_run_registry"].snapshot()
        if snapshot and snapshot.finished_at:
            break
        sleep(0.02)
    app.run()
    assert not app.exception
    assert app.session_state["agent_run_registry"].active_id == run_id
    snapshot = app.session_state["agent_run_registry"].snapshot()
    assert snapshot.result is not None
    assert snapshot.result.graph_version == "fixture-langgraph-v2"
    assert any(event.task_id == "planner" for event in snapshot.events)
    assert any(event.task_id == "scheduler" for event in snapshot.events)
    assert any("Planner" in info.value for info in app.info)
    app.run()
    assert app.session_state["agent_run_registry"].active_id == run_id
