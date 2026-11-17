"""Only explicitly approved static summaries belong in event streams."""

from datetime import datetime, timezone

from dubai_planner.domain.events import ExecutionEvent

SUMMARIES = {
    "run_started": "Planning started",
    "agent_started": "Specialist started",
    "provider_result": "Data lookup completed",
    "artifact_ready": "Artifact ready",
    "validation_finding": "Validation finding available",
    "revision_started": "Revision started",
    "plan_changed": "Plan updated",
    "run_completed": "Run completed",
}


def safe_event(kind: str, run_id: str, sequence: int) -> ExecutionEvent:
    return ExecutionEvent(
        id=f"{run_id}:{sequence}",
        run_id=run_id,
        sequence=sequence,
        timestamp=datetime.now(timezone.utc),
        kind=kind,
        summary=SUMMARIES[kind],
    )
