from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from .base import Identifier, Model, utc


class ExecutionEvent(Model):
    id: Identifier
    run_id: Identifier
    task_id: Identifier | None = None
    revision: int = Field(default=0, strict=True, ge=0, le=2)
    sequence: int = Field(strict=True, ge=0)
    timestamp: datetime
    kind: Literal[
        "run_started",
        "agent_started",
        "provider_result",
        "artifact_ready",
        "validation_finding",
        "revision_started",
        "plan_changed",
        "run_completed",
    ]
    summary: str = Field(max_length=500)
    artifact_ids: list[Identifier] = Field(default_factory=list)
    _utc = field_validator("timestamp")(utc)
