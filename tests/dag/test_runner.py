import random

import pytest

from schemas.dag.v1.contracts import EventIntent, TaskState
from vidur.dag.executor import DagExecutor
from vidur.dag.runner import DagRunner, SimulationFailure


def test_terminal_only_and_nonzero_submission(graph_factory):
    runner = DagRunner()
    callbacks = []
    def callback(gid, now):
        callbacks.append((gid, now))
        return ()
    runner.submit(graph_factory({}), 4, callback)
    assert runner.run() == 4
    graph = runner.executor.graphs["synthetic"]
    assert graph.finished_at - graph.submitted_at == 0
    assert callbacks == [("synthetic", 4)]


def test_long_zero_duration_chain_is_iterative(graph_factory):
    size = 1500
    graph = graph_factory({str(i): 0 for i in range(size)},
                          tuple((str(i), str(i+1)) for i in range(size-1)))
    runner = DagRunner()
    runner.submit(graph)
    assert runner.run() == 0
    assert len(runner.events) == size + 1
    assert all(t.completion_count == 1 for t in runner.executor.graphs[graph.graph_id].tasks.values())


def test_stable_same_time_events_and_multiple_graphs(graph_factory):
    traces = []
    for _ in range(3):
        runner = DagRunner()
        for gid in ("first", "second"):
            runner.submit(graph_factory({"A": 1, "B": 1, "C": 0},
                                       (("A", "C"), ("B", "C")), gid))
        runner.run()
        traces.append(runner.events)
        assert len(runner.executor.graphs) == 2
        with pytest.raises(ValueError, match="duplicate"):
            runner.submit(graph_factory({}, graph_id="first"))
    assert traces[0] == traces[1] == traces[2]
    assert [(e["graph_id"], e["task_id"]) for e in traces[0][:4]] == [
        ("first", "A"), ("first", "B"), ("second", "A"), ("second", "B")]


def test_random_dags_match_independent_critical_path(graph_factory):
    rng = random.Random(20261102)
    for size in (1, 5, 20, 50):
        for case in range(5):
            durations = {str(i): rng.randrange(0, 8) * 1e-6 for i in range(size)}
            edges = tuple((str(i), str(j)) for i in range(size) for j in range(i+1, size)
                          if rng.random() < 0.12)
            starts, ends = {}, {}
            for tid in durations:
                starts[tid] = max((ends[a] for a, b in edges if b == tid), default=0)
                ends[tid] = starts[tid] + durations[tid]
            runner = DagRunner()
            runner.submit(graph_factory(durations, edges))
            runner.run()
            graph = runner.executor.graphs["synthetic"]
            for tid in durations:
                assert graph.tasks[tid].start_at == pytest.approx(starts[tid], abs=1e-15)
                assert graph.tasks[tid].end_at == pytest.approx(ends[tid], abs=1e-15)
            assert graph.finished_at == pytest.approx(max(ends.values()), abs=1e-15)


def test_runner_rejects_past_events_and_future_submit_skipping_pending_work(graph_factory):
    runner = DagRunner()
    runner.submit(graph_factory({"A": 1}), 3)
    with pytest.raises(ValueError, match="earlier"):
        runner.submit(graph_factory({}, graph_id="later"), 5)
    with pytest.raises(ValueError, match="past"):
        runner.enqueue((EventIntent(2, "dispatch", ("synthetic", "A")),))
    assert runner.now == 3
    assert runner.run() == 4


def test_callback_event_return_and_invalid_callback(graph_factory):
    runner = DagRunner()
    runner.submit(graph_factory({}), terminal_callback=lambda gid, now: (
        EventIntent(now, "dispatch", (gid, "terminal")),))
    runner.run()
    assert [e["kind"] for e in runner.events] == ["task_complete", "dispatch"]
    invalid = DagRunner()
    invalid.submit(graph_factory({}), terminal_callback=lambda *_: None)
    with pytest.raises(SimulationFailure, match="EventIntents"):
        invalid.run()
    graph = invalid.executor.graphs["synthetic"]
    assert graph.callback_count == 1 and graph.state == "FAILED"


@pytest.mark.parametrize("now", [-1, True, "1", float("inf"), float("nan")])
def test_invalid_host_time(graph_factory, now):
    executor = DagExecutor()
    with pytest.raises(ValueError):
        executor.submit(graph_factory({}), now, lambda *_: ())
    assert not executor.graphs


def test_completion_time_overflow_fails_graph(graph_factory):
    runner = DagRunner()
    runner.submit(graph_factory({"A": 1e308}), 1e308)
    with pytest.raises(SimulationFailure, match="overflow"):
        runner.run()
    graph = runner.executor.graphs["synthetic"]
    assert graph.tasks["A"].state == TaskState.FAILED
    assert graph.callback_count == 0


def test_positive_duration_cannot_silently_become_zero(graph_factory):
    runner = DagRunner()
    runner.submit(graph_factory({"A": 1}), 1e20)
    with pytest.raises(SimulationFailure, match="precision"):
        runner.run()
    assert runner.executor.graphs["synthetic"].tasks["A"].start_at is None


def test_enqueue_is_atomic_and_failed_runner_rejects_more_work(graph_factory):
    runner = DagRunner()
    runner.submit(graph_factory({"A": 1}), 2)
    before = runner.pending_event_count
    with pytest.raises(ValueError, match="past"):
        runner.enqueue((EventIntent(3, "dispatch", ("synthetic", "A")),
                        EventIntent(1, "dispatch", ("synthetic", "A"))))
    assert runner.pending_event_count == before
    runner.enqueue((EventIntent(2, "graph_failed", ("synthetic", "A")),))
    with pytest.raises(SimulationFailure):
        runner.run()
    with pytest.raises(SimulationFailure):
        runner.submit(graph_factory({}, graph_id="later"))
    assert "later" not in runner.executor.graphs
