from datetime import datetime, timezone
from types import SimpleNamespace

from dubai_planner.ui.agent_view import AGENTS, graph_dot, task_status


def event(task, kind, sequence=0):
    return SimpleNamespace(
        task_id=task,
        kind=kind,
        sequence=sequence,
        summary="x",
        timestamp=datetime.now(timezone.utc),
    )


def test_task_status_lights_follow_event_kinds():
    events = [event("parse", "agent_started"), event("parse", "artifact_ready")]
    events += [event("destination", "agent_started")]
    assert task_status(events, "parse") == "done"
    assert task_status(events, "destination") == "running"
    assert task_status(events, "planner") == "waiting"
    assert task_status(events, "destination", finished=True, failed=True) == "stopped"
    assert task_status(events, "destination", finished=True, failed=False) == "running"


def test_graph_dot_colours_nodes_and_shows_the_loop():
    events = [event("parse", "agent_started"), event("parse", "artifact_ready")]
    dot = graph_dot(events)
    assert dot.startswith("digraph") and dot.rstrip().endswith("}")
    assert '"parse" [fillcolor="#c9f2d4"' in dot  # done = green
    assert '"planner" [fillcolor="#f1f1f1"' in dot  # waiting = grey
    for node in ("research", "destination", "preliminary", "decide", "repair", "finish"):
        assert f'"{node}"' in dot
    assert '"decide" -> "repair"' in dot and '"repair" -> "planner"' in dot


def test_every_agent_has_a_graph_task_and_summary_role():
    assert [label for label, _, _ in AGENTS][-1] == "Review"
    assert len({task for _, task, _ in AGENTS}) == 7
