"""Versioned Phase 7 matrix; live model repetitions are explicit and opt-in."""

import argparse
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event
from time import monotonic

from dubai_planner.agents.fixtures import FixtureSpecialist
from dubai_planner.config import load_settings
from dubai_planner.domain.requests import Constraint, Travelers, TripRequest
from dubai_planner.providers.policy import PolicyRegistry
from dubai_planner.services.run_service import run_fixture, run_model
from dubai_planner.storage.repository import read_catalog
from dubai_planner.system_safety import workspace_write_path

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 15, 18, tzinfo=timezone.utc)


class DuplicateOnce(FixtureSpecialist):
    def __init__(self):
        super().__init__("logistics")

    def execute(self, request, context):
        output = super().execute(request, context)
        if context.stage == "schedule" and context.revision == 0:
            copy = output.days[0].activities[0].model_copy(deep=True)
            copy.id += "-duplicate"
            output.days[0].activities.append(copy)
        return output


class AlwaysBroken(FixtureSpecialist):
    def __init__(self):
        super().__init__("logistics")

    def execute(self, request, context):
        output = super().execute(request, context)
        if context.stage == "schedule":
            output.days[0].activities[0].participants += 1
        return output


def request_for(identifier, baseline):
    data = baseline.model_dump(mode="json")
    data["id"] = "release-" + identifier
    if identifier == "one-day":
        data["days"] = 1
        data["departure"] = data["arrival"]
        data["nights"] = 0
        data["check_in"] = data["check_out"] = None
        data["candidate_ids"] = data["candidate_ids"][:1]
    elif identifier == "seven-day":
        data["days"] = 7
        data["departure"] = (baseline.arrival + timedelta(days=6)).isoformat()
    elif identifier == "adult-and-child":
        data["travelers"] = Travelers(adults=2, child_age_bands=["6-12"]).model_dump(mode="json")
        data["rooms"] = 1
    elif identifier == "ambiguous-budget":
        data["budget"] = None
        data["budget_scope"] = None
    elif identifier == "low-cap":
        data["budget"] = "100"
    elif identifier == "expired-or-unknown-fee":
        for field in ("arrival", "departure", "check_in", "check_out"):
            data[field] = (getattr(baseline, field) + timedelta(days=20)).isoformat()
    elif identifier == "unsupported-accessibility":
        data["constraints"].append(
            Constraint(
                id="wheelchair-step-free",
                field="accessibility",
                operator="includes",
                value="verified step-free access",
            ).model_dump(mode="json")
        )
    return TripRequest.model_validate(data)


def provenance(result):
    available = {source.id for source in result.sources}
    references = {
        reference for finding in result.findings for reference in finding.evidence_ids
    } | {reference for stay in result.accommodation for reference in stay.evidence_ids}
    return 1.0 if not references else len(references & available) / len(references)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--repetitions", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    specification = json.loads((ROOT / "evaluation/release-scenarios.json").read_text())
    repetitions = args.repetitions or specification["default_repetitions"]
    if repetitions < 1 or repetitions > 5:
        parser.error("repetitions must be between 1 and 5")
    settings = load_settings(env_file=args.env_file)
    catalog = read_catalog(ROOT / "data/curated/dubai-seed.json")
    registry = PolicyRegistry.load(ROOT / "config/provider_policies/sources.json")
    baseline = TripRequest.model_validate_json(
        (ROOT / "evaluation/phase2-request.json").read_text()
    )
    rows = []
    for scenario in specification["scenarios"]:
        identifier = scenario["id"]
        # Live runs cover the stable normal request; failure mechanics stay fixture-based.
        count = repetitions if identifier == "four-day-normal" else 1
        for repetition in range(count):
            request = request_for(identifier, baseline)
            cancelled = Event()
            if identifier == "cancelled":
                cancelled.set()
            specialists = None
            if identifier in {"duplicate-repair", "no-progress"}:
                specialist = DuplicateOnce() if identifier == "duplicate-repair" else AlwaysBroken()
                specialists = {
                    role: specialist if role == "logistics" else FixtureSpecialist(role)
                    for role in ("orchestrator", "destination", "logistics", "budget", "reviewer")
                }
            started = monotonic()
            common = dict(
                settings=settings,
                base_id="area-dubai-marina",
                accommodation_id="rove-marina-quote-flex",
                cancelled=cancelled,
                evidence_now=NOW,
            )
            if args.live and identifier == "four-day-normal":
                result = run_model(request, catalog, registry, **common)
            else:
                # Custom specialists exercise LangGraph repair/no-progress routes directly.
                if specialists:
                    from dubai_planner.orchestration.interface import RunContext
                    from dubai_planner.orchestration.langgraph_runner import LangGraphRunner

                    context = RunContext(
                        "eval-" + identifier,
                        datetime.now(timezone.utc)
                        + timedelta(seconds=settings.run_timeout_seconds),
                        cancelled,
                        "phase7",
                        catalog.dataset_version,
                        "fixtures-v1",
                    )
                    result = LangGraphRunner(
                        catalog,
                        registry,
                        base_id="area-dubai-marina",
                        accommodation_id="rove-marina-quote-flex",
                        max_revisions=settings.max_revisions,
                        specialists=specialists,
                        evidence_now=NOW,
                    ).run(request, context, lambda event: None)
                else:
                    result = run_fixture(request, catalog, registry, **common)
            rows.append(
                {
                    "scenario": identifier,
                    "repetition": repetition + 1,
                    "status": result.status,
                    "expected": result.status in scenario["expected"],
                    "revisions": result.revisions,
                    "provenance_completeness": provenance(result),
                    "latency_ms": int((monotonic() - started) * 1000),
                    "metrics": result.metrics,
                }
            )
    outcome_counts = Counter(row["status"] for row in rows)
    report = {
        "schema_version": "1.0",
        "evaluation": "live-model" if args.live else "fixture-release-baseline",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "dataset_version": catalog.dataset_version,
        "sample_size": len(rows),
        "configured_repetitions": repetitions,
        "expected_outcome_rate": sum(row["expected"] for row in rows) / len(rows),
        "mean_provenance_completeness": sum(row["provenance_completeness"] for row in rows)
        / len(rows),
        "outcomes": dict(outcome_counts),
        "accepted": all(row["expected"] for row in rows),
        "runs": rows,
    }
    rendered = json.dumps(report, indent=2)
    if args.output:
        workspace_write_path(args.output, purpose="Evaluation report").write_text(
            rendered + "\n", encoding="utf-8"
        )
    print(rendered)
    return 0 if report["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
