from dataclasses import replace
import heapq
from itertools import count
from pathlib import Path

import pytest

from schemas.dag.v1.contracts import TaskState
from vidur.dag.executor import DagExecutor
from vidur.dag.serialization import load_graph

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/dag/v1"


def drain(executor, initial_events):
    queue, sequence = [], count()
    for event in initial_events:
        heapq.heappush(queue, (event.time_s, next(sequence), event))
    while queue:
        now, _, event = heapq.heappop(queue)
        assert event.kind == "task_complete"
        for intent in executor.on_task_complete(*event.owner, now):
            heapq.heappush(queue, (intent.time_s, next(sequence), intent))


@pytest.mark.parametrize("name,total", [("serial", 10e-6), ("fork_join", 7e-6)])
def test_execute_actual_graph(name, total):
    import json
    graph = load_graph(FIXTURES / f"{name}.graph.json")
    executor = DagExecutor(dependency_only=True)
    callbacks = []
    def callback(gid, now):
        callbacks.append((gid, now))
        return ()
    handle = executor.submit(graph, 0, callback)
    drain(executor, handle.initial_events)
    result = executor.graphs[graph.graph_id]
    expected = json.loads((FIXTURES / f"{name}.expected.json").read_text())["scenarios"][0]
    for tid, interval in expected["schedule_s"].items():
        task = result.tasks[tid]
        assert (task.start_at, task.end_at) == pytest.approx(interval, abs=1e-15)
        assert task.state == TaskState.COMPLETED
        assert task.completion_count == 1
    assert result.finished_at == pytest.approx(total, abs=1e-15)
    assert result.callback_count == len(callbacks) == 1


def test_join_waits_for_all_predecessors_and_rejects_duplicate_completion():
    executor = DagExecutor(dependency_only=True)
    graph = load_graph(FIXTURES / "fork_join.graph.json")
    events = executor.submit(graph, 0, lambda *_: ()).initial_events
    assert [e.owner[1] for e in events] == ["T1", "T2"]
    assert executor.dispatch(0) == ()
    assert executor.on_task_complete("fork_join", "T1", events[0].time_s) == ()
    assert executor.graphs["fork_join"].tasks["T3"].remaining_predecessors == 1
    with pytest.raises(RuntimeError, match="RUNNING"):
        executor.on_task_complete("fork_join", "T1", events[0].time_s)
    assert executor.graphs["fork_join"].tasks["T3"].remaining_predecessors == 1


def test_invalid_completion_does_not_advance_clock():
    executor = DagExecutor(dependency_only=True)
    event = executor.submit(load_graph(FIXTURES / "serial.graph.json"), 0, lambda *_: ()).initial_events[0]
    with pytest.raises(RuntimeError, match="time mismatch"):
        executor.on_task_complete(*event.owner, 1)
    assert executor.now == 0
    executor.on_task_complete(*event.owner, event.time_s)
    with pytest.raises(ValueError, match="backwards"):
        executor.dispatch(0)


def test_submit_failure_atomic_and_resource_mode_explicit():
    executor = DagExecutor()
    graph = load_graph(FIXTURES / "serial.graph.json")
    with pytest.raises(ValueError, match="require"):
        executor.submit(graph, 10, lambda *_: ())
    assert executor.graphs == {} and executor.now == 0
    invalid = replace(graph, edges=((*graph.edges, ("terminal", "T1"))))
    with pytest.raises(ValueError, match="cycle"):
        executor.submit(invalid, 10, lambda *_: ())
    assert executor.graphs == {} and executor.now == 0


def test_inspection_does_not_expose_mutable_runtime():
    executor = DagExecutor(dependency_only=True)
    executor.submit(load_graph(FIXTURES / "serial.graph.json"), 0, lambda *_: ())
    snapshot = executor.graphs
    snapshot["serial"].tasks["T1"].state = TaskState.FAILED
    assert executor.graphs["serial"].tasks["T1"].state == TaskState.RUNNING
