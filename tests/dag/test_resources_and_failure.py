from dataclasses import replace

import pytest

from schemas.dag.v1.contracts import EventIntent, ResourceDemand, TaskState
from vidur.dag.executor import DagExecutor
from vidur.dag.runner import DagRunner, SimulationFailure
from vidur.dag.testing import DependencyOnlyResources


def with_demand(graph, task_id, resource_id="gpu:0", unit="permits"):
    return replace(graph, tasks=tuple(
        replace(t, demands=(ResourceDemand(resource_id, 1, unit),)) if t.task_id == task_id else t
        for t in graph.tasks))


def test_rejected_resource_registry_is_atomic(graph_factory):
    manager = DependencyOnlyResources()
    executor = DagExecutor(manager, resource_units={"gpu:0": "bytes"})
    graph = with_demand(graph_factory({"A": 1}), "A")
    with pytest.raises(ValueError, match="unit mismatch"):
        executor.submit(graph, 0, lambda *_: ())
    assert manager.acquires == [] and executor.graphs == {}


def test_actual_multi_resource_demands_are_forwarded_as_one_request(graph_factory):
    manager = DependencyOnlyResources()
    graph = graph_factory({"A": 1})
    demands = (ResourceDemand("gpu:0", 1, "permits"), ResourceDemand("nic:0", 2, "permits"))
    graph = replace(graph, tasks=(replace(graph.tasks[0], demands=demands), graph.tasks[1]))
    runner = DagRunner(DagExecutor(manager, resource_units={"gpu:0": "permits", "nic:0": "permits"}))
    runner.submit(graph)
    assert manager.active[("synthetic", "A")].demands == demands
    runner.run()
    assert manager.releases.count(("synthetic", "A")) == 1 and not manager.active


def test_placement_does_not_create_implicit_resource_demands(graph_factory):
    from schemas.dag.v1.contracts import Placement
    graph = graph_factory({"A": 1})
    graph = replace(graph, tasks=(replace(graph.tasks[0], placement=Placement(("gpu:unknown",))), graph.tasks[1]))
    runner = DagRunner()
    runner.submit(graph)
    assert runner.run() == 1


def test_cross_graph_wakeup_skips_blocked_and_preserves_submission_order(graph_factory):
    class Gate(DependencyOnlyResources):
        def release(self, lease, now):
            super().release(lease, now)
            wakeups = tuple(reversed(sorted(self.blocked)))
            self.blocked.clear()
            return wakeups
    manager = Gate()
    manager.blocked = {("first", "A"), ("first", "B")}
    runner = DagRunner(DagExecutor(manager))
    runner.submit(graph_factory({"A": 1, "B": 1}, graph_id="first"))
    runner.submit(graph_factory({"A": 2}, graph_id="second"))
    runner.run()
    graphs = runner.executor.graphs
    assert graphs["second"].tasks["A"].start_at == 0
    for tid in ("A", "B"):
        task = graphs["first"].tasks[tid]
        assert task.start_at == 2 and task.resource_wait_s == 2
        assert task.completion_count == 1
    after_second_started = manager.acquires.index(("second", "A")) + 1
    assert manager.acquires[after_second_started:after_second_started+2] == [("first", "A"), ("first", "B")]
    assert len(manager.releases) == 5 and not manager.active


def test_external_dispatch_wakes_waiter(graph_factory):
    manager = DependencyOnlyResources()
    manager.blocked.add(("synthetic", "A"))
    runner = DagRunner(DagExecutor(manager))
    runner.submit(graph_factory({"A": 1}))
    manager.blocked.clear()
    runner.enqueue((EventIntent(3, "dispatch", ("synthetic", "A")),))
    assert runner.run() == 4
    assert runner.executor.graphs["synthetic"].tasks["A"].resource_wait_s == 3


def test_queue_exhaustion_is_not_success(graph_factory):
    manager = DependencyOnlyResources()
    manager.blocked.add(("synthetic", "A"))
    runner = DagRunner(DagExecutor(manager))
    runner.submit(graph_factory({"A": 1}))
    with pytest.raises(SimulationFailure, match="unfinished"):
        runner.run()
    graph = runner.executor.graphs["synthetic"]
    assert graph.tasks["A"].state == TaskState.READY and graph.callback_count == 0


def test_failure_releases_once_ignores_stale_completions_and_never_calls_callback(graph_factory):
    manager = DependencyOnlyResources()
    executor = DagExecutor(manager)
    callbacks = []
    initial = executor.submit(graph_factory({"A": 2, "B": 3, "C": 1},
                                           (("A", "C"), ("B", "C"))), 0,
                              lambda *_: callbacks.append(True)).initial_events
    failed = executor.fail_task("synthetic", "A", 1, "injected task failure")
    assert len(failed) == 1 and failed[0].kind == "graph_failed"
    assert not manager.active and len(manager.releases) == 2
    for event in initial:
        assert executor.on_task_complete(*event.owner, event.time_s) == ()
    assert executor.dispatch(3) == ()
    assert len(manager.releases) == 2 and callbacks == []
    assert executor.graphs["synthetic"].tasks["C"].state == TaskState.PENDING
    with pytest.raises(RuntimeError, match="active RUNNING"):
        executor.fail_task("synthetic", "A", 3, "duplicate failure")


def test_acquire_exception_cleans_previous_running_tasks(graph_factory):
    class BrokenAcquire(DependencyOnlyResources):
        def try_acquire(self, owner, demands):
            if owner[1] == "B":
                raise RuntimeError("injected acquire error")
            return super().try_acquire(owner, demands)
    manager = BrokenAcquire()
    runner = DagRunner(DagExecutor(manager))
    runner.submit(graph_factory({"A": 3, "B": 2}))
    with pytest.raises(SimulationFailure, match="acquire error"):
        runner.run()
    assert not manager.active and manager.releases == [("synthetic", "A")]


def test_failed_release_not_retried_or_reported_as_clean(graph_factory):
    class BrokenRelease(DependencyOnlyResources):
        def release(self, lease, now):
            self.releases.append(lease.owner)
            raise RuntimeError("injected release error")
    manager = BrokenRelease()
    runner = DagRunner(DagExecutor(manager))
    runner.submit(graph_factory({"A": 1}))
    with pytest.raises(SimulationFailure, match="release error"):
        runner.run()
    graph = runner.executor.graphs["synthetic"]
    assert graph.tasks["A"].lease is not None
    assert any("not confirmed" in error for error in graph.cleanup_errors)
    assert manager.releases == [("synthetic", "A")]


def test_duplicate_completion_does_not_release_twice(graph_factory):
    manager = DependencyOnlyResources()
    executor = DagExecutor(manager)
    event = executor.submit(graph_factory({"A": 1}), 0, lambda *_: ()).initial_events[0]
    executor.on_task_complete(*event.owner, event.time_s)
    with pytest.raises(RuntimeError, match="RUNNING"):
        executor.on_task_complete(*event.owner, event.time_s)
    assert manager.releases == [("synthetic", "A")]


@pytest.mark.parametrize("mode", ["raise", "past", "reenter"])
def test_terminal_callback_failure_is_once(graph_factory, mode):
    executor = DagExecutor()
    runner = DagRunner(executor)
    def callback(gid, now):
        if mode == "raise":
            raise RuntimeError("callback error")
        if mode == "past":
            return (EventIntent(now-1, "dispatch", (gid, "terminal")),)
        return executor.dispatch(now)
    runner.submit(graph_factory({"A": 2}), terminal_callback=callback)
    with pytest.raises(SimulationFailure):
        runner.run()
    graph = executor.graphs["synthetic"]
    assert graph.callback_count == 1 and graph.state == "FAILED"


def test_inspection_does_not_deepcopy_callback_host(graph_factory):
    class Host:
        def __deepcopy__(self, memo):
            raise RuntimeError("host must not be copied")
        def callback(self, *_):
            return ()
    host = Host()
    executor = DagExecutor()
    executor.submit(graph_factory({}), 0, host.callback)
    assert executor.graphs["synthetic"].callback.__self__ is host
