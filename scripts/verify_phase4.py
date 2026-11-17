"""Small historical fixture-graph verification. No database or network writes."""

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from threading import Event

from dubai_planner.domain.requests import TripRequest
from dubai_planner.orchestration.interface import RunContext
from dubai_planner.orchestration.langgraph_runner import LangGraphRunner
from dubai_planner.providers.policy import PolicyRegistry
from dubai_planner.storage.repository import read_catalog

ROOT = Path(__file__).resolve().parents[1]
AS_OF = datetime(2026, 11, 15, 18, tzinfo=timezone.utc)


def main():
    catalog = read_catalog(ROOT / "data/curated/dubai-seed.json")
    registry = PolicyRegistry.load(ROOT / "config/provider_policies/sources.json")
    catalog.check_policy(registry, "export")
    trip = TripRequest.model_validate_json((ROOT / "evaluation/phase2-request.json").read_text())
    rows = []
    for name, budget, clock, expected in [
        ("historical", Decimal("5000"), AS_OF, "validated_estimate"),
        ("budget_repair", Decimal("4140"), AS_OF, "validated_estimate"),
        ("expired_quote", Decimal("5000"), AS_OF + timedelta(days=2), "partial"),
    ]:
        request = trip.model_copy(deep=True)
        request.budget = budget
        events = []
        context = RunContext(
            run_id="verify-" + name,
            deadline=datetime.now(timezone.utc) + timedelta(seconds=30),
            cancelled=Event(),
            configuration_hash="historical-verification",
            dataset_version=catalog.dataset_version,
            prompt_version="fixtures-v1",
        )
        result = LangGraphRunner(
            catalog,
            registry,
            base_id="area-dubai-marina",
            accommodation_id="rove-marina-quote-flex",
            evidence_now=clock,
        ).run(request, context, events.append)
        assert result.status == expected
        if name == "budget_repair":
            assert result.revisions == 1
            assert result.accommodation[0].id == "rove-marina-quote-nonrefund"
        rows.append(
            dict(
                scenario=name,
                status=result.status,
                revisions=result.revisions,
                stop_reason=result.metrics["stop_reason"],
                events=len(events),
                total_high=str(result.budget.total_high),
                accommodation=result.accommodation[0].id,
            )
        )
    print(
        json.dumps(
            dict(
                dataset_version=catalog.dataset_version,
                evidence_as_of=AS_OF.isoformat(),
                scope="Historical fixture verification; not current availability or model-driven agents.",
                scenarios=rows,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
