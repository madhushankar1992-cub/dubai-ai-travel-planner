import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier, Event
from urllib.error import HTTPError

import pytest

from dubai_planner.agents.model_specialist import ReviewAdvice, Selection, extract_request
from dubai_planner.config import Settings
from dubai_planner.orchestration.interface import RunContext
from dubai_planner.services.llm_gateway import ModelFailure, ModelGateway, NoRedirect, post_json


def gateway(transport, **settings):
    config = Settings(groq_api_key="secret-groq", gemini_api_key="secret-gemini", **settings)
    context = RunContext(
        "test", datetime.now(timezone.utc) + timedelta(seconds=60), Event(), "hash", "version", "v1"
    )
    return ModelGateway(config, context, transport=transport)


def response(text, finish="stop"):
    return {
        "choices": [{"finish_reason": finish, "message": {"content": text}}],
        "usage": {"total_tokens": 50},
    }


GOOD = json.dumps({"selected_ids": [], "evidence_ids": [], "summary": "No approved choices"})


def test_schema_repair_can_recover_without_echoing_bad_response():
    calls = []

    def transport(url, headers, payload, timeout):
        calls.append(payload)
        return response("private-bad-output" if len(calls) == 1 else GOOD)

    client = gateway(transport)
    assert client.generate("destination", "Return JSON", {}, Selection).selected_ids == []
    assert len(calls) == 2
    assert "private-bad-output" not in json.dumps(calls[1])
    assert client.metrics()["model_calls"] == 2


def test_semantic_fabrication_is_repaired_only_once():
    client = gateway(lambda *args: response(GOOD))

    def reject(output):
        raise ValueError("Unsupported evidence")

    with pytest.raises(ModelFailure, match="invalid_model_output"):
        client.generate("destination", "JSON", {}, Selection, validate=reject)
    assert client.metrics()["model_calls"] == 2


@pytest.mark.parametrize("finish", ["length", "content_filter", None])
def test_truncated_or_blocked_responses_never_become_results(finish):
    client = gateway(lambda *args: response(GOOD, finish))
    with pytest.raises(ModelFailure, match="incomplete_response"):
        client.generate("budget", "JSON", {}, Selection)
    assert client.metrics()["model_calls"] == 1


def test_shared_call_ledger_under_parallel_execution():
    client = gateway(lambda *args: response(GOOD), max_model_calls=1)
    barrier = Barrier(2)

    def call():
        barrier.wait()
        try:
            client.generate("destination", "JSON", {}, Selection)
            return "success"
        except ModelFailure as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: call(), range(2)))
    assert sorted(results) == ["call_limit", "success"]
    assert client.metrics()["model_calls"] == 1


def test_cancellation_discards_late_response():
    client = gateway(lambda *args: response(GOOD))

    def transport(*args):
        client.context.cancelled.set()
        return response(GOOD)

    client.transport = transport
    with pytest.raises(ModelFailure, match="cancelled"):
        client.generate("destination", "JSON", {}, Selection)


def test_http_failure_is_sanitized(monkeypatch):
    class Failing:
        def open(self, *args, **kwargs):
            raise HTTPError("secret-url", 401, "secret-response", {}, None)

    monkeypatch.setattr("dubai_planner.services.llm_gateway.build_opener", lambda *args: Failing())
    with pytest.raises(ModelFailure, match="authentication") as exc:
        post_json("https://api.groq.com/openai/v1/chat/completions", {}, {}, 1)
    assert "secret" not in str(exc.value)
    with pytest.raises(ModelFailure, match="host_rejected"):
        post_json("https://attacker.example", {}, {}, 1)
    with pytest.raises(ModelFailure, match="redirect_rejected"):
        NoRedirect().redirect_request(None, None, 302, "", {}, "https://attacker.example")


def test_provider_error_details_are_classified_without_leaking(monkeypatch):
    class Response:
        status = 403

        def read(self, limit):
            return json.dumps(
                {
                    "error": {
                        "message": "Organization verification is required; secret-token",
                        "type": "permission_error",
                    }
                }
            ).encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class Failing:
        def open(self, *args, **kwargs):
            error = HTTPError("safe", 403, "forbidden", {}, None)
            error.read = Response().read
            raise error

    monkeypatch.setattr("dubai_planner.services.llm_gateway.build_opener", lambda *args: Failing())
    with pytest.raises(ModelFailure, match="organization_verification_required") as exc:
        post_json("https://api.groq.com/openai/v1/chat/completions", {}, {}, 1)
    assert "secret-token" not in str(exc.value)


def test_rate_limit_honors_bounded_retry_after(monkeypatch):
    class Response:
        def read(self, limit):
            return json.dumps({"ok": True}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class Flaky:
        calls = 0

        def open(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise HTTPError("safe", 429, "limited", {"Retry-After": "0.1"}, None)
            return Response()

    delays = []
    flaky = Flaky()
    monkeypatch.setattr("dubai_planner.services.llm_gateway.build_opener", lambda *args: flaky)
    monkeypatch.setattr("dubai_planner.services.llm_gateway.sleep", delays.append)
    assert post_json("https://api.groq.com/openai/v1/chat/completions", {}, {}, 1) == {"ok": True}
    assert flaky.calls == 2
    assert delays == [0.6]


def test_gemini_reviewer_falls_back_to_local_ollama_only():
    calls = []

    def transport(url, headers, payload, timeout):
        calls.append((url, headers, payload))
        if "generativelanguage" in url:
            raise ModelFailure("invalid_provider_request")
        return {
            "done": True,
            "done_reason": "stop",
            "message": {"content": json.dumps({"observations": [], "summary": "Review complete."})},
            "prompt_eval_count": 40,
            "eval_count": 10,
        }

    client = gateway(transport, ollama_base_url="http://127.0.0.1:11434/api")
    result = client.generate("reviewer", "Review", {}, ReviewAdvice)
    assert result.observations == []
    assert ["generativelanguage" in call[0] for call in calls] == [True, False]
    assert calls[1][0] == "http://127.0.0.1:11434/api/chat"
    assert calls[1][2]["model"] == "devstral:24b"
    assert calls[1][2]["stream"] is False
    assert client.metrics()["review_provider"] == "ollama"
    assert client.metrics()["review_fallbacks"] == 1


def test_ollama_primary_routes_non_review_agents_and_keeps_fallbacks_configured():
    calls = []

    def transport(url, headers, payload, timeout):
        calls.append((url, payload))
        return {
            "done": True,
            "done_reason": "stop",
            "message": {"content": GOOD},
            "prompt_eval_count": 30,
            "eval_count": 20,
        }

    client = gateway(transport, ollama_api_key="secret-ollama", model_routing="ollama-primary")
    result = client.generate("destination", "Select", {}, Selection)
    assert result.selected_ids == []
    assert calls[0][0] == "https://ollama.com/api/chat"
    assert calls[0][1]["model"] == "devstral:24b"
    assert client.metrics()["calls_provider_ollama"] == 1


def test_secondary_ollama_key_enables_ollama_when_primary_is_unset():
    observed_headers = []

    def transport(url, headers, payload, timeout):
        observed_headers.append(headers)
        return {
            "done": True,
            "done_reason": "stop",
            "message": {"content": GOOD},
            "prompt_eval_count": 30,
            "eval_count": 20,
        }

    client = gateway(
        transport,
        ollama_api_key=None,
        ollama_api_key_secondary="secondary-ollama-secret",
        model_routing="ollama-primary",
    )
    assert client.generate("destination", "Select", {}, Selection).selected_ids == []
    assert observed_headers[0]["Authorization"] == "Bearer secondary-ollama-secret"


def test_local_ollama_uses_the_local_allowlisted_endpoint_without_an_api_key():
    observed = []

    def transport(url, headers, payload, timeout):
        observed.append((url, headers, payload))
        return {
            "done": True,
            "done_reason": "stop",
            "message": {"content": GOOD},
            "prompt_eval_count": 30,
            "eval_count": 20,
        }

    client = gateway(
        transport,
        ollama_api_key=None,
        ollama_base_url="http://127.0.0.1:11434/api",
        ollama_model="qwen3:8b",
        model_routing="ollama-primary",
    )
    assert client.generate("destination", "Select", {}, Selection).selected_ids == []
    assert observed[0][0] == "http://127.0.0.1:11434/api/chat"
    assert observed[0][1].get("Authorization") is None
    assert observed[0][2]["model"] == "qwen3:8b"


@pytest.mark.parametrize(
    ("role", "schema", "content", "expected_providers"),
    [
        ("destination", Selection, GOOD, {"groq", "ollama"}),
        (
            "reviewer",
            ReviewAdvice,
            json.dumps({"observations": [], "summary": "Review complete."}),
            {"gemini", "ollama"},
        ),
    ],
)
def test_parallel_ensemble_calls_both_role_providers_concurrently(
    role, schema, content, expected_providers
):
    barrier = Barrier(2)
    called = []

    def transport(url, headers, payload, timeout):
        provider = (
            "groq" if "groq.com" in url else "gemini" if "generativelanguage" in url else "ollama"
        )
        called.append(provider)
        barrier.wait(timeout=2)
        if provider == "groq":
            return response(content)
        if provider == "gemini":
            return {
                "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": content}]}}],
                "usageMetadata": {"totalTokenCount": 50},
            }
        return {
            "done": True,
            "done_reason": "stop",
            "message": {"content": content},
            "prompt_eval_count": 30,
            "eval_count": 20,
        }

    client = gateway(transport, ollama_api_key="secret-ollama", model_routing="parallel-ensemble")
    client.generate(role, "Return JSON", {}, schema)
    assert set(called) == expected_providers
    assert client.metrics()["ensemble_roles"] == 1
    assert client.metrics()["ensemble_partial"] == 0


def test_extraction_returns_proposal_with_missing_information():
    output = json.dumps(
        {
            "request": None,
            "clarification_fields": ["days"],
            "summary": "Please supply trip duration.",
        }
    )
    client = gateway(lambda *args: response(output))
    result = extract_request("I want a Dubai trip", client)
    assert result.request is None
    assert result.clarification_fields == ["days"]
    assert client.metrics()["calls_orchestrator"] == 1
