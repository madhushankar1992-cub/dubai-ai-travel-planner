import json
from datetime import timedelta
from pathlib import Path

import pytest

from dubai_planner.config import Settings, load_settings
from dubai_planner.domain.requests import TripRequest
from dubai_planner.services.llm_gateway import ModelFailure
from dubai_planner.services.run_service import run_model


def settings(**overrides):
    return Settings(
        groq_api_key="test-groq-secret", gemini_api_key="test-gemini-secret", **overrides
    )


class MockProviders:
    """Provider-shaped responses, never claimed as real model execution evidence."""

    def __init__(self, *, invalid=None, fail=None):
        self.calls = []
        self.invalid = invalid
        self.fail = fail

    def __call__(self, url, headers, payload, timeout):
        gemini = "generativelanguage" in url
        data = json.loads(
            payload["contents"][0]["parts"][0]["text"]
            if gemini
            else payload["messages"][1]["content"]
        )
        stage = data.get("task", "extract")
        self.calls.append((stage, url, payload))
        assert 0 < timeout <= 90
        assert "test-groq-secret" not in json.dumps(payload)
        assert "test-gemini-secret" not in json.dumps(payload)
        if self.fail == stage:
            raise ModelFailure("quota_exhausted")
        records = data.get("candidates", [])
        evidence = sorted({e for r in records for e in r["evidence_ids"]})
        answer = {"summary": "Supported local selection; retain all disclosed limitations."}
        if stage == "parse":
            answer.update(
                selected_ids=[],
                evidence_ids=[],
                clarification_fields=data["required_clarifications"],
            )
        elif stage in {"research", "plan", "schedule"}:
            answer.update(selected_ids=[r["id"] for r in records], evidence_ids=evidence)
            if stage == "plan":
                answer["clarification_fields"] = []
        elif stage == "preliminary":
            stay = data["accommodation"][0]
            answer.update(accommodation_id=stay["id"], evidence_ids=stay["evidence_ids"])
        elif stage == "cost":
            if data["alternative_required"]:
                stay = next(
                    a for a in data["accommodation"] if a["id"] == "rove-marina-quote-nonrefund"
                )
                answer.update(alternative_accommodation_ids=[stay["id"]])
            else:
                answer.update(alternative_accommodation_ids=[])
        elif stage == "review":
            answer["observations"] = []
        elif stage == "extract":
            answer.update(request=None, clarification_fields=["days"])
        if self.invalid == stage:
            answer["fabricated_price"] = "0"
        if gemini:
            return {
                "candidates": [
                    {"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(answer)}]}}
                ],
                "usageMetadata": {"totalTokenCount": 100},
            }
        return {
            "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(answer)}}],
            "usage": {"total_tokens": 100},
        }


def execute(catalog, registry, now, transport, *, trip=None, config=None):
    return run_model(
        trip or TripRequest.model_validate_json(Path("evaluation/phase2-request.json").read_text()),
        catalog,
        registry,
        settings=config or settings(),
        transport=transport,
        evidence_now=now,
        base_id="area-dubai-marina",
        accommodation_id="rove-marina-quote-flex",
    )


def test_all_five_model_roles_use_requested_providers(catalog, registry, now):
    providers = MockProviders()
    result = execute(catalog, registry, now, providers)
    assert result.status == "validated_estimate", result.metrics
    assert result.graph_version == "model-langgraph-v2"
    assert result.metrics["model_calls"] == 7
    assert result.metrics["model_tokens"] == 700
    assert len(result.agent_summaries) == 7
    for role in (
        "orchestrator",
        "destination",
        "logistics",
        "planner",
        "scheduler",
        "budget",
        "reviewer",
    ):
        assert result.metrics["calls_" + role] > 0
    for stage, url, payload in providers.calls:
        assert ("generativelanguage.googleapis.com" in url) == (stage == "review")
        if stage == "review":
            assert payload["generationConfig"]["responseMimeType"] == "application/json"
    assert "Fixture agents only" not in result.model_dump_json()


def test_model_budget_repair_rechecks_with_gemini(catalog, registry, now):
    providers = MockProviders()
    trip = TripRequest.model_validate_json(Path("evaluation/phase2-request.json").read_text())
    trip.budget = "4140"
    result = execute(catalog, registry, now, providers, trip=trip)
    assert result.status == "validated_estimate", result.metrics
    assert result.revisions == 1
    assert result.accommodation[0].id == "rove-marina-quote-nonrefund"
    assert result.metrics["calls_reviewer"] == 2
    assert result.metrics["calls_budget"] == 2
    assert result.request == trip


def test_gemini_cannot_clear_deterministic_errors(catalog, registry, now):
    result = execute(catalog, registry, now + timedelta(days=2), MockProviders())
    assert result.status == "partial"
    assert any(f.rule_id == "BUDGET_UNKNOWN" for f in result.findings)


@pytest.mark.parametrize("invalid", ["research", "schedule", "review"])
def test_exactly_one_schema_repair_then_no_fixture_fallback(catalog, registry, now, invalid):
    providers = MockProviders(invalid=invalid)
    result = execute(catalog, registry, now, providers)
    assert result.status == "failed"
    assert result.metrics["stop_reason"] == "invalid_model_output"
    assert sum(stage == invalid for stage, _, _ in providers.calls) == 2


def test_provider_unavailable_has_clear_safe_failure(catalog, registry, now):
    result = execute(catalog, registry, now, MockProviders(fail="review"))
    assert result.status == "failed"
    assert result.metrics["stop_reason"] == "quota_exhausted"


@pytest.mark.parametrize("limit", ["calls", "tokens"])
def test_shared_limits(catalog, registry, now, limit):
    config = settings(**({"max_model_calls": 1} if limit == "calls" else {"max_model_tokens": 1}))
    providers = MockProviders()
    result = execute(catalog, registry, now, providers, config=config)
    assert result.status == "failed"
    assert result.metrics["stop_reason"] == ("call_limit" if limit == "calls" else "token_limit")
    assert len(providers.calls) <= 1


def test_missing_keys_never_falls_back(catalog, registry, now):
    with pytest.raises(ModelFailure, match="missing_GROQ"):
        execute(catalog, registry, now, MockProviders(), config=Settings())


def test_local_env_is_data_only_and_secrets_are_excluded(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        'GROQ_API_KEY="local-secret"\nGEMINI_API_KEY=gemini-secret\nGROQ_MODEL=model-name\n'
    )
    loaded = load_settings({}, env_file=env_file)
    assert loaded.capabilities["model_runner"]
    assert "local-secret" not in repr(loaded)
    assert "local-secret" not in loaded.model_dump_json()
    assert load_settings({"GROQ_MODEL": "env-first"}, env_file=env_file).groq_model == "env-first"
    env_file.write_text("GROQ_MODEL=$(unsafe-command)\n")
    with pytest.raises(ValueError, match="Invalid configuration"):
        load_settings({}, env_file=env_file)


def test_export_policy_checked_before_model_calls(catalog, registry, now):
    providers = MockProviders()
    registry.policies[catalog.evidence[0].source_id].export = False
    with pytest.raises(ValueError):
        execute(catalog, registry, now, providers)
    assert not providers.calls


class ShortDestination(MockProviders):
    """Destination research that always under-selects."""

    def __init__(self):
        super().__init__()

    def __call__(self, url, headers, payload, timeout):
        response = super().__call__(url, headers, payload, timeout)
        stage = self.calls[-1][0]
        if stage == "research":
            body = json.loads(response["choices"][0]["message"]["content"])
            body["selected_ids"] = body["selected_ids"][:1]
            response["choices"][0]["message"]["content"] = json.dumps(body)
        return response


def test_last_resort_guard_tops_up_and_discloses_it(catalog, registry, now):
    result = execute(catalog, registry, now, ShortDestination())
    guard = [line for line in result.agent_summaries if "coverage guard added" in line]
    assert guard and guard[0].startswith("destination/")
    assert result.status != "failed"
    assert result.metrics["model_calls"] == 7  # no repair spent on a short answer


class ScramblingScheduler(MockProviders):
    """Scheduler that drops a stop, repeats one and invents an ID."""

    def __call__(self, url, headers, payload, timeout):
        response = super().__call__(url, headers, payload, timeout)
        if self.calls[-1][0] == "schedule":
            body = json.loads(response["choices"][0]["message"]["content"])
            body["selected_ids"] = [body["selected_ids"][0]] * 2 + ["not-a-real-place"]
            response["choices"][0]["message"]["content"] = json.dumps(body)
        return response


def test_scheduler_order_is_repaired_by_python_not_a_failed_run(catalog, registry, now):
    result = execute(catalog, registry, now, ScramblingScheduler())
    assert result.status != "failed", result.metrics
    assert result.metrics["model_calls"] == 7  # no repair attempt wasted on the ordering
    scheduled = [a.place_id for day in result.days for a in day.activities]
    assert len(scheduled) == len(set(scheduled)) >= 1
