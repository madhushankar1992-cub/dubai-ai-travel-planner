from threading import Event
from time import sleep

from dubai_planner.domain.review import PlanResult
from dubai_planner.observability.redaction import safe_event
from dubai_planner.services.run_service import SessionRunRegistry


def failed(run_id, request):
    return PlanResult(run_id=run_id, request=request, status="failed")


def test_registry_deduplicates_and_keeps_immutable_request(request_model):
    registry = SessionRunRegistry()
    release = Event()
    received = []

    def execute(run_id, request, emit, cancelled):
        release.wait(2)
        received.append(request.days)
        emit(safe_event("run_started", run_id, 0))
        return failed(run_id, request)

    first = registry.start(
        request_model, mode="fixture", configuration={"dataset": "v1"}, execute=execute
    )
    duplicate = registry.start(
        request_model, mode="fixture", configuration={"dataset": "v1"}, execute=execute
    )
    request_model.days = 1
    release.set()
    assert first == duplicate
    for _ in range(1000):
        snapshot = registry.snapshot()
        if snapshot and snapshot.finished_at:
            break
        sleep(0.001)
    assert received == [4]
    assert snapshot.request.days == 4
    assert snapshot.result.request.days == 4
    assert len(snapshot.events) == 1


def test_newer_active_run_cannot_be_replaced_by_late_result(request_model):
    registry = SessionRunRegistry()
    old_release = Event()
    new_release = Event()

    def old(run_id, request, emit, cancelled):
        old_release.wait(2)
        return failed(run_id, request)

    def new(run_id, request, emit, cancelled):
        new_release.wait(2)
        return failed(run_id, request)

    old_id = registry.start(request_model, mode="fixture", configuration={"n": 1}, execute=old)
    new_id = registry.start(request_model, mode="fixture", configuration={"n": 2}, execute=new)
    old_release.set()
    assert registry.active_id == new_id
    assert registry.snapshot().run_id == new_id
    assert registry.snapshot(old_id).run_id == old_id
    assert registry.cancel(new_id)
    new_release.set()
    for _ in range(1000):
        snapshot = registry.snapshot(new_id)
        if snapshot and snapshot.finished_at:
            break
        sleep(0.001)
    assert snapshot.state == "cancelled"
