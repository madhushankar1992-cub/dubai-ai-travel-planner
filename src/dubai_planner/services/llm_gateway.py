"""Small REST gateway: allowlisted hosts, bounded responses, shared run limits."""

import json
import re
from datetime import datetime, timezone
from io import BytesIO
from threading import Lock
from time import monotonic, sleep
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from pydantic import ValidationError

from dubai_planner.agents.prompts import VERSION as PROMPT_VERSION


class ModelFailure(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__("Model request stopped: " + code)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ModelFailure("redirect_rejected")


def post_json(url, headers, payload, timeout):
    if not (
        url == "https://api.groq.com/openai/v1/chat/completions"
        or url.startswith("https://generativelanguage.googleapis.com/v1beta/models/")
    ):
        raise ModelFailure("host_rejected")
    body = json.dumps(payload).encode()
    opener = build_opener(NoRedirect(), ProxyHandler({}))
    last_error = None
    for attempt in range(4):
        try:
            with opener.open(
                Request(url, data=body, headers=headers, method="POST"), timeout=timeout
            ) as response:
                raw = response.read(1_000_001)
            if len(raw) > 1_000_000:
                raise ModelFailure("response_too_large")
            return json.loads(raw)
        except HTTPError as exc:
            if exc.code == 429 and attempt < 3:
                value = exc.headers.get("Retry-After", "")
                if not value:
                    value = exc.headers.get("x-ratelimit-reset-tokens", "")
                match = re.search(r"\d+(?:\.\d+)?", value)
                delay = min(float(match.group()) + 0.5, 45.0) if match else 10.0 * (attempt + 1)
                sleep(delay)
                continue
            if exc.code in {500, 502, 503, 504} and attempt < 3:
                sleep(1.0 * (2**attempt))
                continue
            if exc.code == 400 and attempt < 3:
                # Groq JSON mode answers 400 when the model's own JSON was malformed. That
                # is sampling noise, so the same request is retried rather than failing.
                try:
                    raw_error = exc.read(8192)
                except OSError:
                    raw_error = b""
                if b"json_validate_failed" in raw_error or b"Failed to generate JSON" in raw_error:
                    sleep(0.5)
                    continue
                exc.fp = BytesIO(raw_error)
            last_error = exc
            break
        except (URLError, TimeoutError, OSError):
            raise ModelFailure("network_or_timeout") from None
        except (ValueError, UnicodeError):
            raise ModelFailure("invalid_provider_response") from None
    exc = last_error
    code = {
        401: "authentication",
        403: "access_denied",
        404: "model_unavailable",
        429: "quota_exhausted",
        500: "provider_server_error",
        502: "provider_server_error",
        503: "provider_server_error",
        504: "provider_server_error",
    }.get(exc.code, "provider_http_" + str(exc.code))
    if exc.code in {400, 403}:
        try:
            detail = json.loads(exc.read(8192)).get("error", {})
            category = " ".join(
                str(detail.get(key, "")) for key in ("code", "type", "message")
            ).casefold()
            if "organization" in category and ("verify" in category or "verification" in category):
                code = "organization_verification_required"
            elif "content" in category or "safety" in category or "blocked" in category:
                code = "provider_content_blocked"
            elif "model" in category and (
                "access" in category or "permission" in category or "allowed" in category
            ):
                code = "model_access_denied"
            elif "token" in category or "context" in category:
                code = "provider_token_limit"
            elif exc.code == 400:
                code = "invalid_provider_request"
        except (AttributeError, TypeError, ValueError, OSError):
            if exc.code == 400:
                code = "invalid_provider_request"
    raise ModelFailure(code) from None


def clip_summary(text, schema_json):
    """Trim an over-long free-text ``summary``; every other field stays strictly validated.

    The summary is non-authoritative display prose. Rejecting an otherwise valid answer
    because the model wrote a few characters too many wasted a repair attempt and could
    fail the whole run.
    """
    limit = schema_json.get("properties", {}).get("summary", {}).get("maxLength")
    if not isinstance(limit, int) or limit < 2:
        return text
    try:
        data = json.loads(text)
    except ValueError:
        return text
    summary = data.get("summary") if isinstance(data, dict) else None
    if isinstance(summary, str) and len(summary) > limit:
        data["summary"] = summary[: limit - 1].rstrip() + "…"
        return json.dumps(data, ensure_ascii=False)
    return text


class ModelGateway:
    def __init__(self, settings, context, *, transport=post_json):
        if not (settings.groq_api_key and settings.gemini_api_key):
            raise ModelFailure("missing_GROQ_API_KEY_or_GEMINI_API_KEY")
        self.settings, self.context, self.transport = settings, context, transport
        self.lock = Lock()
        self.calls = self.tokens = self.reserved = self.latency_ms = 0
        self.role_calls = {}
        self.provider_calls = {}
        self.provider_failures = {}
        self.validation_failures = []
        self.review_provider = ""

    def check(self):
        if self.context.cancelled.is_set():
            raise ModelFailure("cancelled")
        remaining = (self.context.deadline - datetime.now(timezone.utc)).total_seconds()
        if remaining <= 0:
            raise ModelFailure("deadline")
        return min(remaining, self.settings.model_timeout_seconds)

    def metrics(self):
        with self.lock:
            return {
                "model_calls": self.calls,
                "model_tokens": self.tokens,
                "model_latency_ms": self.latency_ms,
                "groq_model": self.settings.groq_model,
                "gemini_model": self.settings.gemini_model,
                "review_provider": self.review_provider,
                "prompt_version": PROMPT_VERSION,
                "model_output_tokens": self.settings.model_output_tokens,
                "model_sampling": "provider-default",
                "model_validation_failures": len(self.validation_failures),
                "model_validation_last": (
                    json.dumps(self.validation_failures[-1], separators=(",", ":"))
                    if self.validation_failures
                    else ""
                ),
                **{"calls_" + role: count for role, count in self.role_calls.items()},
                **{
                    "calls_provider_" + provider: count
                    for provider, count in self.provider_calls.items()
                },
                **{
                    "failures_" + provider + "_" + code: count
                    for (provider, code), count in self.provider_failures.items()
                },
            }

    def generate(self, role, prompt, data, schema, *, validate=lambda output: output):
        # Groq runs every agent except Review; Gemini runs Review. There is no fallback
        # provider: a failure is reported rather than silently routed elsewhere.
        provider = "gemini" if role == "reviewer" else "groq"
        try:
            result = self._generate_provider(
                provider, role, prompt, data, schema, validate=validate
            )
        except ModelFailure as exc:
            with self.lock:
                key = (provider, exc.code)
                self.provider_failures[key] = self.provider_failures.get(key, 0) + 1
            raise
        if role == "reviewer":
            with self.lock:
                self.review_provider = provider
        return result

    def _generate_provider(
        self, provider, role, prompt, data, schema, *, validate=lambda output: output
    ):
        output_tokens = self.settings.model_output_tokens
        if role in {"budget", "reviewer"}:
            output_tokens = max(output_tokens, 2048)
        schema_json = schema.model_json_schema()
        # A single schema/semantic repair per task, counted against the same ledger.
        hint = ""
        for attempt in range(2):
            system = (
                prompt
                + "\nReturn only a JSON object matching this schema:\n"
                + json.dumps(schema_json)
            )
            if attempt:
                system += "\nPrevious output failed validation. Recreate from the supplied data, using only allowed IDs and evidence. Do not add fields."
                if hint:
                    system += " Problem: " + hint
            user = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
            # UTF-8 byte count + framing is a conservative input-token reservation.
            input_bound = len((system + user).encode()) + 512
            reserve = input_bound + output_tokens
            with self.lock:
                timeout = self.check()
                if self.calls >= self.settings.max_model_calls:
                    raise ModelFailure("call_limit")
                if self.tokens + self.reserved + reserve > self.settings.max_model_tokens:
                    raise ModelFailure("token_limit")
                self.calls += 1
                self.reserved += reserve
                self.role_calls[role] = self.role_calls.get(role, 0) + 1
                self.provider_calls[provider] = self.provider_calls.get(provider, 0) + 1
            started = monotonic()
            usage = reserve  # Failed calls retain their reservation as consumed.
            try:
                if provider == "groq":
                    payload = {
                        "model": self.settings.groq_model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        "response_format": {"type": "json_object"},
                        "max_completion_tokens": output_tokens,
                    }
                    url = "https://api.groq.com/openai/v1/chat/completions"
                    headers = {
                        "Authorization": "Bearer " + self.settings.groq_api_key.get_secret_value(),
                        "Content-Type": "application/json",
                        "User-Agent": "dubai-planner/1.0",
                    }
                elif provider == "gemini":
                    payload = {
                        "systemInstruction": {"parts": [{"text": system}]},
                        "contents": [{"role": "user", "parts": [{"text": user}]}],
                        "generationConfig": {
                            "responseMimeType": "application/json",
                            "maxOutputTokens": output_tokens,
                        },
                    }
                    url = (
                        "https://generativelanguage.googleapis.com/v1beta/models/"
                        + self.settings.gemini_model
                        + ":generateContent"
                    )
                    headers = {
                        "x-goog-api-key": self.settings.gemini_api_key.get_secret_value(),
                        "Content-Type": "application/json",
                        "User-Agent": "dubai-planner/1.0",
                    }
                response = self.transport(url, headers, payload, timeout)
                self.check()
                if provider == "groq":
                    choice = response["choices"][0]
                    if choice.get("finish_reason") != "stop":
                        raise ModelFailure("incomplete_response")
                    text = choice["message"]["content"]
                    reported = response.get("usage", {}).get("total_tokens")
                elif provider == "gemini":
                    choice = response["candidates"][0]
                    if choice.get("finishReason") != "STOP":
                        raise ModelFailure("incomplete_response")
                    text = "".join(
                        p.get("text", "")
                        for p in choice["content"]["parts"]
                        if not p.get("thought")
                    )
                    reported = response.get("usageMetadata", {}).get("totalTokenCount")
                if type(reported) is int and reported > 0:
                    usage = reported
                if usage > reserve:
                    raise ModelFailure("token_limit")
                if not isinstance(text, str) or len(text.encode()) > 100_000:
                    raise ModelFailure("invalid_provider_response")
                parsed = schema.model_validate_json(clip_summary(text, schema_json))
                return validate(parsed)
            except ModelFailure:
                raise
            except ValidationError as exc:
                safe_errors = [
                    {
                        "location": ".".join(str(part) for part in error["loc"]),
                        "type": error["type"],
                    }
                    for error in exc.errors(include_input=False, include_context=False)[:8]
                ]
                hint = "; ".join(f"{e['location']} {e['type']}" for e in safe_errors)[:300]
                with self.lock:
                    self.validation_failures.append(
                        {"role": role, "kind": "schema", "errors": safe_errors}
                    )
                if attempt:
                    raise ModelFailure("invalid_model_output") from None
            except ValueError as exc:
                # Validator messages are fixed strings that never echo model output.
                hint = re.sub(r"[^A-Za-z0-9 ,.:_-]", "", str(exc))[:160]
                with self.lock:
                    self.validation_failures.append({"role": role, "kind": "semantic"})
                if attempt:
                    raise ModelFailure("invalid_model_output") from None
            except (KeyError, IndexError, TypeError):
                raise ModelFailure("invalid_provider_response") from None
            except Exception as exc:
                raise ModelFailure("provider_error_" + type(exc).__name__.lower()) from None
            finally:
                with self.lock:
                    self.reserved -= reserve
                    self.tokens += usage
                    self.latency_ms += int((monotonic() - started) * 1000)
