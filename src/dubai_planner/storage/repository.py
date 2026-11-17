"""Atomic immutable catalog versions; validation precedes every database mutation."""

import csv
import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from dubai_planner.providers.policy import PolicyDenied, PolicyRegistry
from dubai_planner.system_safety import workspace_write_path

from .catalog import Catalog

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY);
INSERT OR IGNORE INTO schema_migrations VALUES (1);
CREATE TABLE IF NOT EXISTS datasets (
 version TEXT PRIMARY KEY, digest TEXT NOT NULL, payload TEXT NOT NULL, imported_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS active_dataset (singleton INTEGER PRIMARY KEY CHECK(singleton=1), version TEXT NOT NULL REFERENCES datasets(version));
"""


class ImportRejected(ValueError):
    def __init__(self, report: Path):
        super().__init__(f"Dataset rejected; see import report: {report}")
        self.report = report


def read_catalog(path: Path) -> Catalog:
    if path.stat().st_size > 10_000_000:
        raise ValueError("Dataset exceeds the 10 MB import limit")
    if path.suffix.lower() == ".json":
        return Catalog.model_validate_json(path.read_text(encoding="utf-8"))
    if path.suffix.lower() == ".csv":
        data = {
            key: []
            for key in ("evidence", "places", "accommodation", "prices", "routes", "tariffs")
        }
        metadata_seen = False
        with path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != ["kind", "payload"]:
                raise ValueError("CSV columns must be kind,payload (JSON object per payload)")
            for row in reader:
                kind, payload = row["kind"], json.loads(row["payload"])
                if kind == "metadata" and not metadata_seen:
                    if set(payload) != {"schema_version", "dataset_version"}:
                        raise ValueError("Invalid CSV metadata")
                    data.update(payload)
                    metadata_seen = True
                elif kind in data and isinstance(data[kind], list):
                    data[kind].append(payload)
                else:
                    raise ValueError("Unknown CSV kind or duplicate metadata")
        if not metadata_seen:
            raise ValueError("CSV metadata row required")
        return Catalog.model_validate(data)
    raise ValueError("Only JSON and CSV imports are supported")


class CatalogRepository:
    def __init__(self, database: Path, registry: PolicyRegistry):
        self.database = workspace_write_path(database, purpose="Database")
        self.registry = registry

    def import_file(self, path: Path, report_dir: Path) -> dict:
        return self._import(lambda: read_catalog(path), report_dir)

    def import_json(self, payload: str, report_dir: Path, *, expected_version=None) -> dict:
        def load():
            if len(payload.encode("utf-8")) > 10_000_000:
                raise ValueError("Dataset exceeds the 10 MB import limit")
            return Catalog.model_validate_json(payload)

        return self._import(load, report_dir, expected_version=expected_version)

    def _import(self, loader, report_dir: Path, *, expected_version=None) -> dict:
        report_dir = workspace_write_path(report_dir, purpose="Import report")
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"import-{uuid4().hex}.json"
        report = {"accepted": False, "dataset_version": None, "errors": []}
        try:
            catalog = loader()
            catalog.check_policy(self.registry, "persist")
            report["dataset_version"] = catalog.dataset_version
            payload = json.dumps(
                catalog.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
            )
            digest = hashlib.sha256(payload.encode()).hexdigest()
            # Validation is complete. All SQL values are bound parameters.
            self.database.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(self.database)) as db:
                db.execute("PRAGMA foreign_keys=ON")
                db.executescript(SCHEMA)
                with db:
                    db.execute("BEGIN IMMEDIATE")
                    active = db.execute(
                        "SELECT version FROM active_dataset WHERE singleton=1"
                    ).fetchone()
                    if expected_version is not None and (
                        not active or active[0] != expected_version
                    ):
                        raise ValueError("Catalog changed in another session; reload before saving")
                    existing = db.execute(
                        "SELECT digest FROM datasets WHERE version=?", (catalog.dataset_version,)
                    ).fetchone()
                    if existing and existing[0] != digest:
                        raise ValueError(
                            "Dataset version already exists with different content; publish a new version"
                        )
                    db.execute(
                        "INSERT OR IGNORE INTO datasets VALUES (?,?,?,?)",
                        (
                            catalog.dataset_version,
                            digest,
                            payload,
                            datetime.now(timezone.utc).isoformat(),
                        ),
                    )
                    db.execute(
                        "INSERT INTO active_dataset VALUES (1,?) ON CONFLICT(singleton) DO UPDATE SET version=excluded.version",
                        (catalog.dataset_version,),
                    )
            report.update(
                accepted=True,
                digest=digest,
                unchanged=bool(existing),
                counts={
                    key: len(getattr(catalog, key))
                    for key in (
                        "places",
                        "prices",
                        "routes",
                        "accommodation",
                        "evidence",
                        "tariffs",
                    )
                },
            )
        except ValidationError as exc:
            report["errors"] = [
                {"location": list(e["loc"]), "type": e["type"], "message": e["msg"]}
                for e in exc.errors(include_input=False, include_context=False)
            ]
        except (ValueError, OSError, sqlite3.Error, PolicyDenied) as exc:
            report["errors"] = [{"type": type(exc).__name__, "message": str(exc)}]
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        if not report["accepted"]:
            raise ImportRejected(report_path)
        return {**report, "report_path": str(report_path)}

    def load(self) -> Catalog:
        if not self.database.exists():
            raise FileNotFoundError("Catalog missing; run dubai-data import first")
        uri = self.database.resolve().as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as db:
            row = db.execute(
                "SELECT payload FROM datasets JOIN active_dataset ON datasets.version=active_dataset.version WHERE singleton=1"
            ).fetchone()
        if not row:
            raise ValueError("No active catalog")
        catalog = Catalog.model_validate_json(row[0])
        catalog.check_policy(self.registry, "read")
        return catalog

    def export(self, destination: Path):
        destination = workspace_write_path(destination, purpose="Export")
        catalog = self.load()
        catalog.check_policy(self.registry, "export")
        if destination.suffix.lower() == ".json":
            destination.write_text(catalog.model_dump_json(indent=2), encoding="utf-8")
        elif destination.suffix.lower() == ".csv":
            data = catalog.model_dump(mode="json")
            with destination.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.writer(stream)
                writer.writerow(["kind", "payload"])
                writer.writerow(
                    [
                        "metadata",
                        json.dumps({k: data[k] for k in ("schema_version", "dataset_version")}),
                    ]
                )
                for kind in ("evidence", "places", "accommodation", "prices", "routes", "tariffs"):
                    for record in data[kind]:
                        writer.writerow([kind, json.dumps(record)])
        else:
            raise ValueError("Export extension must be .json or .csv")
