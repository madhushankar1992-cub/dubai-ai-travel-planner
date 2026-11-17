"""Explicit live-provider acceptance; prints only safe metadata, never prompts or keys."""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from dubai_planner.config import load_settings
from dubai_planner.domain.requests import TripRequest
from dubai_planner.providers.policy import PolicyRegistry
from dubai_planner.services.llm_gateway import ModelFailure
from dubai_planner.services.run_service import run_model
from dubai_planner.storage.repository import read_catalog

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(
        description="Calls Groq and Gemini using your configured accounts"
    )
    parser.add_argument("--env-file", type=Path)
    parser.add_argument(
        "--historical-evidence",
        action="store_true",
        help="Evaluate the November 15 evidence snapshot; never claim current availability",
    )
    args = parser.parse_args()
    settings = load_settings(env_file=args.env_file)
    catalog = read_catalog(ROOT / "data/curated/dubai-seed.json")
    registry = PolicyRegistry.load(ROOT / "config/provider_policies/sources.json")
    now = datetime(2026, 11, 15, 18, tzinfo=timezone.utc) if args.historical_evidence else None
    rows = []
    for name, cap in (("normal", "5000"), ("budget_repair", "4140")):
        request = TripRequest.model_validate_json(
            (ROOT / "evaluation/phase2-request.json").read_text()
        )
        request.budget = cap
        events = []
        result = run_model(
            request,
            catalog,
            registry,
            settings=settings,
            base_id="area-dubai-marina",
            accommodation_id="rove-marina-quote-flex",
            evidence_now=now,
            emit_event=events.append,
        )
        all_roles = all(
            result.metrics.get("calls_" + role, 0) > 0
            for role in (
                "orchestrator",
                "destination",
                "logistics",
                "planner",
                "scheduler",
                "budget",
                "reviewer",
            )
        )
        passed = all_roles and result.validation_complete
        if name == "budget_repair":
            passed = passed and result.revisions > 0 and result.metrics.get("calls_reviewer", 0) > 1
            passed = passed and result.status == "validated_estimate"
        rows.append(
            dict(
                scenario=name,
                status=result.status,
                revisions=result.revisions,
                all_roles_called=all_roles,
                accepted=passed,
                metrics=result.metrics,
                events=len(events),
            )
        )
        if not passed:
            break  # Do not consume another run after a failed acceptance scenario.
    report = dict(
        verification="live-providers",
        evidence_clock=now.isoformat() if now else "current",
        checked_at=datetime.now(timezone.utc).isoformat(),
        dataset=catalog.dataset_version,
        scenarios=rows,
        accepted=len(rows) == 2 and all(row["accepted"] for row in rows),
    )
    print(json.dumps(report, indent=2))
    return 0 if report["accepted"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, ModelFailure):
        print(
            json.dumps(
                {
                    "accepted": False,
                    "reason": "Check private provider configuration; live verification did not complete.",
                }
            )
        )
        raise SystemExit(1) from None
