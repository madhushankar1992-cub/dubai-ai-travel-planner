"""Validate a single reviewed record against the complete catalog before saving."""

import json
from datetime import datetime, timezone
from uuid import uuid4

from dubai_planner.storage.catalog import Catalog

COLLECTIONS = ("places", "accommodation", "prices", "routes", "tariffs", "evidence")


def edited_catalog(catalog, collection, record_json, *, original_id=None):
    if collection not in COLLECTIONS:
        raise ValueError("Unknown record collection")
    if len(record_json.encode("utf-8")) > 100_000:
        raise ValueError("A single record must be smaller than 100 KB")
    record = json.loads(record_json)
    if not isinstance(record, dict) or not isinstance(record.get("id"), str):
        raise ValueError("Supply one JSON object with a record ID")
    if original_id and record["id"] != original_id:
        raise ValueError("Keep the existing ID to preserve references")
    payload = catalog.model_dump(mode="json")
    records = payload[collection]
    existing = next((i for i, row in enumerate(records) if row["id"] == record["id"]), None)
    if original_id:
        if existing is None:
            raise ValueError("Record no longer exists; reload")
        records[existing] = record
    else:
        if existing is not None:
            raise ValueError("ID already exists; choose edit instead")
        records.append(record)
    payload["dataset_version"] = (
        datetime.now(timezone.utc).strftime("%Y-%m-%d") + ".local-" + uuid4().hex[:10]
    )
    for evidence in payload["evidence"]:
        evidence["dataset_version"] = payload["dataset_version"]
    # Deliberately preserve review timestamps; editing is not a freshness refresh.
    return Catalog.model_validate(payload)
