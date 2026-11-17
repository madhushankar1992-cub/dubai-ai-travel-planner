import json
import socket

import pytest

from dubai_planner.providers.gateway import ProviderGateway
from dubai_planner.providers.local import LocalProvider
from dubai_planner.providers.policy import PolicyDenied
from dubai_planner.storage.repository import CatalogRepository, ImportRejected, read_catalog


def test_atomic_repeatable_import_and_csv(tmp_path, catalog, registry):
    source = tmp_path / "seed.json"
    source.write_text(catalog.model_dump_json(), encoding="utf-8")
    repo = CatalogRepository(tmp_path / "catalog.sqlite", registry)
    first = repo.import_file(source, tmp_path / "reports")
    second = repo.import_file(source, tmp_path / "reports")
    assert first["accepted"] and second["unchanged"] and first["digest"] == second["digest"]
    repo.export(tmp_path / "roundtrip.csv")
    assert read_catalog(tmp_path / "roundtrip.csv") == catalog
    bad = catalog.model_dump(mode="json")
    bad["places"].append(bad["places"][0])
    source.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ImportRejected) as exc:
        repo.import_file(source, tmp_path / "reports")
    assert json.loads(exc.value.report.read_text())["errors"]
    assert repo.load() == catalog


def test_policy_revocation(tmp_path, catalog, registry):
    registry.policies["editorial"].approved = False
    with pytest.raises(PolicyDenied):
        catalog.check_policy(registry)
    registry.policies["editorial"].approved = True
    registry.policies["editorial"].export = False
    with pytest.raises(PolicyDenied):
        catalog.check_policy(registry, "export")


def test_local_gateway_without_network(tmp_path, catalog, registry, monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("Local mode must not access the network")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    source = tmp_path / "seed.json"
    source.write_text(catalog.model_dump_json(), encoding="utf-8")
    repo = CatalogRepository(tmp_path / "catalog.sqlite", registry)
    repo.import_file(source, tmp_path / "reports")
    gateway = ProviderGateway(repo)
    assert gateway.search_places().data
    assert gateway.get_place_details("dubai-frame").data.name == "Dubai Frame"
    assert gateway.search_accommodation().data
    assert gateway.route("absent", "missing", "taxi").data is None
    assert gateway.get_price("absent").status == "unavailable"


def test_freshness_and_missing(catalog, now):
    from datetime import timedelta

    provider = LocalProvider(catalog, now=lambda: now + timedelta(days=365))
    assert provider.get_price("dubai-frame").freshness == "stale"
    assert provider.get_price("al-fahidi").status == "unavailable"
    assert provider.route("a", "b", "flying").status == "unsupported"
