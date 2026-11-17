"""Thread-safe, in-memory events with static summaries and retry deduplication."""

from threading import RLock

from dubai_planner.observability.redaction import safe_event


def merge_records(left, right):
    """Append by ID; identical retries are harmless, conflicting facts are not."""
    merged = {item.id: item for item in left}
    for item in right:
        if item.id in merged and merged[item.id] != item:
            raise ValueError("Conflicting shared record ID")
        merged[item.id] = item
    return list(merged.values())


class EventSink:
    def __init__(self, run_id, callback):
        self.run_id = run_id
        self.callback = callback
        self.events = {}
        self.lock = RLock()

    def emit(self, kind, task, revision=0, artifacts=()):
        key = (kind, task, revision, tuple(artifacts))
        with self.lock:
            if key not in self.events:
                event = safe_event(kind, self.run_id, len(self.events))
                event.task_id = task
                event.revision = revision
                event.artifact_ids = list(artifacts)
                self.events[key] = event
                self.callback(event.model_copy(deep=True))
            return self.events[key]
