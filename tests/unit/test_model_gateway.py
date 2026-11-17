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


def test_groq_runs_planning_roles_and_gemini_runs_review():
    calls = []
    review = json.dumps({"observations": [], "summary": "Review complete."})

    def transport(url, headers, payload, timeout):
        calls.append(url)
        if "generativelanguage" in url:
            return {
                "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": review}]}}],
                "usageMetadata": {"totalTokenCount": 50},
            }
        return response(GOOD)

    client = gateway(transport)
    assert client.generate("destination", "Select", {}, Selection).selected_ids == []
    assert client.generate("reviewer", "Review", {}, ReviewAdvice).observations == []
    assert calls[0] == "https://api.groq.com/openai/v1/chat/completions"
    assert calls[1].startswith("https://generativelanguage.googleapis.com/v1beta/models/")
    metrics = client.metrics()
    assert metrics["calls_provider_groq"] == 1 and metrics["calls_provider_gemini"] == 1
    assert metrics["review_provider"] == "gemini"


def test_provider_failure_is_reported_without_any_fallback_provider():
    calls = []

    def transport(url, headers, payload, timeout):
        calls.append(url)
        raise ModelFailure("provider_server_error")

    client = gateway(transport)
    with pytest.raises(ModelFailure) as caught:
        client.generate("reviewer", "Review", {}, ReviewAdvice)
    assert caught.value.code == "provider_server_error"
    assert len(calls) == 1 and "generativelanguage" in calls[0]
    assert client.metrics()["failures_gemini_provider_server_error"] == 1


def test_only_groq_and_gemini_hosts_are_allowlisted():
    for url in (
        "https://ollama.com/api/chat",
        "http://127.0.0.1:11434/api/chat",
        "https://example.com/v1/chat/completions",
    ):
        with pytest.raises(ModelFailure) as caught:
            post_json(url, {}, {}, 1)
        assert caught.value.code == "host_rejected"


def test_gateway_requires_both_groq_and_gemini_keys():
    context = RunContext(
        "test", datetime.now(timezone.utc) + timedelta(seconds=60), Event(), "hash", "version", "v1"
    )
    for keys in ({"groq_api_key": "g"}, {"gemini_api_key": "g"}, {}):
        with pytest.raises(ModelFailure) as caught:
            ModelGateway(Settings(**keys), context, transport=lambda *a: None)
        assert caught.value.code == "missing_GROQ_API_KEY_or_GEMINI_API_KEY"


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


def test_overlong_summary_is_clipped_but_other_fields_stay_strict():
    import json

    from dubai_planner.services.llm_gateway import clip_summary

    schema = {"properties": {"summary": {"maxLength": 20}}}
    clipped = json.loads(clip_summary(json.dumps({"summary": "x" * 50, "ids": ["a"]}), schema))
    assert len(clipped["summary"]) == 20 and clipped["summary"].endswith("…")
    assert clipped["ids"] == ["a"]
    short = json.dumps({"summary": "fine"})
    assert clip_summary(short, schema) == short
    assert clip_summary("not json", schema) == "not json"
    assert clip_summary(short, {"properties": {}}) == short


def test_repair_prompt_names_the_validation_problem_without_echoing_output():
    calls = []
    bad = json.dumps({"selected_ids": "oops", "evidence_ids": [], "summary": "private-bad-output"})

    def transport(url, headers, payload, timeout):
        calls.append(payload)
        return response(bad if len(calls) == 1 else GOOD)

    client = gateway(transport)
    assert client.generate("destination", "Return JSON", {}, Selection).selected_ids == []
    repair_system = calls[1]["messages"][0]["content"]
    assert "Problem: selected_ids list_type" in repair_system
    assert "private-bad-output" not in json.dumps(calls[1])


def test_semantic_repair_prompt_carries_the_fixed_validator_message():
    calls = []

    def transport(url, headers, payload, timeout):
        calls.append(payload)
        return response(GOOD)

    def validate(output):
        if len(calls) == 1:
            raise ValueError("Select supported candidates")
        return output

    client = gateway(transport)
    client.generate("planner", "Return JSON", {}, Selection, validate=validate)
    assert "Problem: Select supported candidates" in calls[1]["messages"][0]["content"]


def test_groq_malformed_json_400_is_retried_but_other_400s_are_not(monkeypatch):
    from io import BytesIO

    class Response:
        def read(self, limit):
            return json.dumps({"ok": True}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def make(body_for_first):
        class Opener:
            calls = 0

            def open(self, *args, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    raise HTTPError("safe", 400, "bad", {}, BytesIO(body_for_first))
                return Response()

        return Opener()

    monkeypatch.setattr("dubai_planner.services.llm_gateway.sleep", lambda delay: None)
    url = "https://api.groq.com/openai/v1/chat/completions"
    retry = make(b'{"error":{"code":"json_validate_failed","message":"Failed to generate JSON"}}')
    monkeypatch.setattr("dubai_planner.services.llm_gateway.build_opener", lambda *args: retry)
    assert post_json(url, {}, {}, 1) == {"ok": True} and retry.calls == 2
    other = make(b'{"error":{"code":"invalid_request","message":"bad field"}}')
    monkeypatch.setattr("dubai_planner.services.llm_gateway.build_opener", lambda *args: other)
    with pytest.raises(ModelFailure) as caught:
        post_json(url, {}, {}, 1)
    assert caught.value.code == "invalid_provider_request" and other.calls == 1
