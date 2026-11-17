"""Reproduce the reviewed snapshot, not a current booking/availability check."""

import json
from datetime import datetime, timezone
from pathlib import Path

from dubai_planner.domain.requests import TripRequest
from dubai_planner.providers.policy import PolicyRegistry
from dubai_planner.services.planner import plan_local
from dubai_planner.storage.repository import read_catalog

ROOT = Path(__file__).resolve().parents[1]
AS_OF = datetime(2026, 11, 15, 18, tzinfo=timezone.utc)


def main():
    catalog = read_catalog(ROOT / "data/curated/dubai-seed.json")
    registry = PolicyRegistry.load(ROOT / "config/provider_policies/sources.json")
    request = TripRequest.model_validate_json((ROOT / "evaluation/phase2-request.json").read_text())
    results = []
    for suffix in ("flex", "nonrefund"):
        result = plan_local(
            request,
            catalog,
            registry=registry,
            now=AS_OF,
            base_id="area-dubai-marina",
            accommodation_id="rove-marina-quote-" + suffix,
        )
        if result.status != "validated_estimate":
            raise ValueError(result.model_dump_json())
        results.append(
            dict(
                accommodation_id=result.accommodation[0].id,
                status=result.status,
                budget=result.budget.model_dump(mode="json"),
                days=[
                    dict(
                        day=d.day,
                        activities=[a.place_id for a in d.activities],
                        routes=[r.id for r in d.routes],
                    )
                    for d in result.days
                ],
                findings=[f.model_dump(mode="json") for f in result.findings],
            )
        )
    report = dict(
        dataset_version=catalog.dataset_version,
        as_of=AS_OF.isoformat(),
        scope="Historical reproducibility check of the 15 November snapshot, not current rates or availability.",
        assumptions=request.assumptions,
        alternatives=results,
    )
    (ROOT / "evaluation/phase2-result.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "dataset_version": catalog.dataset_version,
                "alternatives": [r["status"] for r in results],
            }
        )
    )


if __name__ == "__main__":
    main()
