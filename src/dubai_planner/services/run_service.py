"""LangGraph entry points and session-scoped background run management."""

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from queue import Empty, SimpleQueue
from threading import Event, RLock
from typing import Callable
from uuid import uuid4

from dubai_planner.agents.prompts import VERSION as PROMPT_VERSION
from dubai_planner.domain.events import ExecutionEvent
from dubai_planner.domain.requests import TripRequest
from dubai_planner.domain.review import PlanResult
from dubai_planner.orchestration.interface import RunContext
from dubai_planner.orchestration.langgraph_runner import LangGraphRunner

_WORKERS = ThreadPoolExecutor(max_workers=4, thread_name_prefix="dubai-planner")


@dataclass
class _ManagedRun:
    run_id: str
    key: str
    mode: str
    request: TripRequest
    cancelled: Event = field(default_factory=Event)
    event_queue: SimpleQueue = field(default_factory=SimpleQueue)
    events: list[ExecutionEvent] = field(default_factory=list)
    result: PlanResult | None = None
    state: str = "queued"
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    lock: RLock = field(default_factory=RLock)


@dataclass(frozen=True)
class RunSnapshot:
    run_id: str
    mode: str
    state: str
    request: TripRequest
    events: tuple[ExecutionEvent, ...]
    result: PlanResult | None
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None


class SessionRunRegistry:
    """Owns one UI session's runs; no record or queue is shared across sessions."""

    def __init__(self):
        self._runs: dict[str, _ManagedRun] = {}
        self._keys: dict[str, str] = {}
        self._active_id: str | None = None
        self._lock = RLock()

    @property
    def active_id(self):
        with self._lock:
            return self._active_id

    def start(
        self,
        request: TripRequest,
        *,
        mode: str,
        configuration: dict,
        execute: Callable[[str, TripRequest, Callable[[ExecutionEvent], None], Event], PlanResult],
    ) -> str:
        request = TripRequest.model_validate(request.model_dump())
        key_payload = {
            "request": request.model_dump(mode="json"),
            "mode": mode,
            "configuration": configuration,
        }
        key = hashlib.sha256(
            json.dumps(key_payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        with self._lock:
            prior_id = self._keys.get(key)
            if prior_id and self._runs[prior_id].state not in {"cancelled", "failed"}:
                self._active_id = prior_id
                return prior_id
            run_id = "ui-" + uuid4().hex
            record = _ManagedRun(run_id=run_id, key=key, mode=mode, request=request)
            self._runs[run_id] = record
            self._keys[key] = run_id
            self._active_id = run_id

        def emit(event):
            # Events from another context can never enter this session record.
            if event.run_id == run_id:
                record.event_queue.put(event.model_copy(deep=True))

        def work():
            with record.lock:
                record.state = "running"
                record.started_at = datetime.now(timezone.utc)
            try:
                result = execute(run_id, request.model_copy(deep=True), emit, record.cancelled)
                result = PlanResult.model_validate(result.model_dump())
                if result.run_id != run_id:
                    raise ValueError("Runner returned a mismatched run ID")
                with record.lock:
                    if record.cancelled.is_set():
                        result = PlanResult(
                            run_id=run_id,
                            graph_version=result.graph_version,
                            request=record.request,
                            status="cancelled",
                            metrics={**result.metrics, "stop_reason": "cancelled"},
                        )
                    record.result = result
                    record.state = "cancelled" if result.status == "cancelled" else "completed"
            except Exception:
                # Provider details, prompts, payloads and credentials never enter UI state.
                with record.lock:
                    record.state = "cancelled" if record.cancelled.is_set() else "failed"
                    record.error = "Planning stopped before a usable result was produced."
            finally:
                with record.lock:
                    record.finished_at = datetime.now(timezone.utc)

        _WORKERS.submit(work)
        return run_id

    def cancel(self, run_id: str) -> bool:
        with self._lock:
            record = self._runs.get(run_id)
        if record is None:
            return False
        with record.lock:
            if record.state in {"completed", "cancelled", "failed"}:
                return False
            record.cancelled.set()
            record.state = "cancel_requested"
            return True

    def snapshot(self, run_id: str | None = None) -> RunSnapshot | None:
        with self._lock:
            selected = run_id or self._active_id
            record = self._runs.get(selected) if selected else None
        if record is None:
            return None
        with record.lock:
            while True:
                try:
                    event = record.event_queue.get_nowait()
                except Empty:
                    break
                if not any(existing.id == event.id for existing in record.events):
                    record.events.append(event)
            return RunSnapshot(
                run_id=record.run_id,
                mode=record.mode,
                state=record.state,
                request=record.request.model_copy(deep=True),
                events=tuple(event.model_copy(deep=True) for event in record.events),
                result=record.result.model_copy(deep=True) if record.result else None,
                started_at=record.started_at,
                finished_at=record.finished_at,
                error=record.error,
            )


def run_fixture(
    request,
    catalog,
    registry,
    *,
    settings,
    base_id="area-bur-dubai",
    accommodation_id=None,
    emit_event=lambda event: None,
    cancelled=None,
    run_id=None,
    evidence_now=None,
):
    context = RunContext(
        run_id=run_id or "fixture-" + uuid4().hex,
        deadline=datetime.now(timezone.utc) + timedelta(seconds=settings.run_timeout_seconds),
        cancelled=cancelled if cancelled is not None else Event(),
        configuration_hash=hashlib.sha256(settings.model_dump_json().encode()).hexdigest()[:16],
        dataset_version=catalog.dataset_version,
        prompt_version="fixtures-v1",
    )
    return LangGraphRunner(
        catalog,
        registry,
        base_id=base_id,
        accommodation_id=accommodation_id,
        max_revisions=settings.max_revisions,
        evidence_now=evidence_now,
    ).run(request, context, emit_event)


def model_session(catalog, settings, *, cancelled=None, transport=None, run_id=None):
    from dubai_planner.services.llm_gateway import ModelGateway

    context = RunContext(
        run_id=run_id or "model-" + uuid4().hex,
        deadline=datetime.now(timezone.utc) + timedelta(seconds=settings.run_timeout_seconds),
        cancelled=cancelled if cancelled is not None else Event(),
        configuration_hash=hashlib.sha256(settings.model_dump_json().encode()).hexdigest()[:16],
        dataset_version=catalog.dataset_version,
        prompt_version=PROMPT_VERSION,
    )
    gateway = ModelGateway(settings, context, **({"transport": transport} if transport else {}))
    return context, gateway


def run_model(
    request,
    catalog,
    registry,
    *,
    settings,
    base_id="area-bur-dubai",
    accommodation_id=None,
    emit_event=lambda event: None,
    cancelled=None,
    transport=None,
    evidence_now=None,
    run_id=None,
):
    from dubai_planner.agents.model_specialist import ModelSpecialist

    # Model-provider transfer is an export, even with no local persistence.
    catalog.check_policy(registry, "read")
    catalog.check_policy(registry, "export")
    context, gateway = model_session(
        catalog, settings, cancelled=cancelled, transport=transport, run_id=run_id
    )
    specialists = {
        role: ModelSpecialist(role, gateway)
        for role in (
            "orchestrator",
            "destination",
            "logistics",
            "planner",
            "scheduler",
            "budget",
            "reviewer",
        )
    }
    return LangGraphRunner(
        catalog,
        registry,
        base_id=base_id,
        accommodation_id=accommodation_id,
        max_revisions=settings.max_revisions,
        specialists=specialists,
        evidence_now=evidence_now,
        mode="model",
        model_metrics=gateway.metrics,
        model_summaries=lambda: [
            summary for specialist in specialists.values() for summary in specialist.summaries
        ],
    ).run(request, context, emit_event)
