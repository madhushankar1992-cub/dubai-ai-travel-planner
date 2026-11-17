from dataclasses import dataclass
from datetime import datetime
from threading import Event
from typing import Callable, Protocol

from dubai_planner.domain.events import ExecutionEvent
from dubai_planner.domain.requests import TripRequest
from dubai_planner.domain.review import PlanResult


@dataclass(frozen=True)
class RunContext:
    run_id: str
    deadline: datetime
    cancelled: Event
    configuration_hash: str
    dataset_version: str
    prompt_version: str


class Runner(Protocol):
    def run(
        self,
        request: TripRequest,
        context: RunContext,
        emit_event: Callable[[ExecutionEvent], None],
    ) -> PlanResult: ...
