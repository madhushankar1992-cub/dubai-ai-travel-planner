"""Small, compressed, immutable plan snapshots in the existing project database."""

import hashlib
import json
import sqlite3
import zlib
from contextlib import closing
from datetime import datetime, timezone

from dubai_planner.domain.review import PlanResult
from dubai_planner.system_safety import workspace_write_path


class PlanRepository:
    def __init__(self, database, registry):
        self.database = workspace_write_path(database, purpose="Plan database")
        self.registry = registry

    def _check(self, result, operation):
        sources = {e.id: e for e in result.sources}
        for evidence in result.sources:
            self.registry.require(evidence.source_id, "evidence", operation)
        for stay in result.accommodation:
            for reference in stay.evidence_ids:
                if reference not in sources:
                    raise ValueError("Accommodation evidence missing from saved result")
                self.registry.require(sources[reference].source_id, "accommodation", operation)

    def save(self, result: PlanResult, label: str):
        label = label.strip()
        if not 1 <= len(label) <= 80:
            raise ValueError("Use a plan name between 1 and 80 characters")
        result = PlanResult.model_validate(result.model_dump())
        self._check(result, "persist")
        payload = json.dumps(
            result.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        ).encode()
        if len(payload) > 10_000_000:
            raise ValueError("Plan exceeds the 10 MB limit")
        identifier = hashlib.sha256(payload).hexdigest()
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.database)) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS saved_plans (id TEXT PRIMARY KEY, label TEXT NOT NULL, created_at TEXT NOT NULL, payload BLOB NOT NULL)"
            )
            with db:
                db.execute(
                    "INSERT OR IGNORE INTO saved_plans VALUES (?,?,?,?)",
                    (
                        identifier,
                        label,
                        datetime.now(timezone.utc).isoformat(),
                        zlib.compress(payload),
                    ),
                )
        return identifier

    def list(self):
        if not self.database.exists():
            return []
        with closing(
            sqlite3.connect(self.database.resolve().as_uri() + "?mode=ro", uri=True)
        ) as db:
            if not db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='saved_plans'"
            ).fetchone():
                return []
            return [
                dict(id=row[0], label=row[1], created_at=row[2])
                for row in db.execute(
                    "SELECT id,label,created_at FROM saved_plans ORDER BY created_at DESC"
                )
            ]

    def load(self, identifier):
        with closing(
            sqlite3.connect(self.database.resolve().as_uri() + "?mode=ro", uri=True)
        ) as db:
            row = db.execute("SELECT payload FROM saved_plans WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise ValueError("Saved plan not found")
        result = PlanResult.model_validate_json(zlib.decompress(row[0]))
        self._check(result, "read")
        return result

    def export(self, result):
        self._check(result, "export")
        return result.model_dump_json(indent=2)
