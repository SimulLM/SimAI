from dataclasses import replace

import pytest

from schemas.dag.v1.contracts import ResourceDemand
from vidur.dag.executor import DagExecutor
from vidur.dag.resources import CapacityResourceManager, ResourceCapacity, resource_timeline
from vidur.dag.runner import DagRunner
from vidur.dag.trace import write_results


def manager():
    return CapacityResourceManager({
        "gpu:0": ResourceCapacity(1, "permits"),
        "nic:0": ResourceCapacity(1, "permits"),
        "kv:0": ResourceCapacity(100, "bytes"),
    })


def with_demands(graph, overrides):
    return replace(graph, tasks=tuple(
        replace(task, demands=tuple(overrides.get(task.task_id, task.demands)))
        for task in graph.tasks
    ))


def run(graph, capacities):
    units = {resource: value.unit for resource, value in capacities._capacities.items()}
    runner = DagRunner(DagExecutor(capacities, resource_units=units))
    runner.submit(graph)
    assert runner.run() >= 0
    return runner


def test_resource_contention_acceptance_cases(graph_factory):
    base = graph_factory({"T1": 10e-6, "T2": 4e-6, "T3": 8e-6},
                         (("T1", "T3"), ("T2", "T3")))
    shared = run(with_demands(base, {
        tid: (ResourceDemand("gpu:0", 1, "permits"),) for tid in ("T1", "T2", "T3")
    }), manager())
    assert shared.now == pytest.approx(22e-6)

    independent = run(with_demands(base, {
        "T1": (ResourceDemand("gpu:0", 1, "permits"),),
        "T2": (ResourceDemand("nic:0", 1, "permits"),),
        "T3": (ResourceDemand("gpu:0", 1, "permits"),),
    }), manager())
    assert independent.now == pytest.approx(18e-6)

    comm_uses_compute = run(with_demands(base, {
        "T1": (ResourceDemand("gpu:0", 1, "permits"),),
        "T2": (ResourceDemand("nic:0", 1, "permits"), ResourceDemand("gpu:0", 1, "permits")),
        "T3": (ResourceDemand("gpu:0", 1, "permits"),),
    }), manager())
    assert comm_uses_compute.now == pytest.approx(22e-6)


def test_multi_resource_failure_is_atomic_and_waiters_wake_in_order():
    capacities = manager()
    first = capacities.try_acquire(("g", "first"), (ResourceDemand("gpu:0", 1, "permits"),))
    assert first is not None
    assert capacities.try_acquire(("g", "wait"), (
        ResourceDemand("gpu:0", 1, "permits"), ResourceDemand("nic:0", 1, "permits"),
    )) is None
    assert capacities.usage_snapshot()["nic:0"]["used"] == 0
    assert capacities.release(first, 2) == (("g", "wait"),)
    acquired = capacities.try_acquire(("g", "wait"), (
        ResourceDemand("gpu:0", 1, "permits"), ResourceDemand("nic:0", 1, "permits"),
    ))
    assert acquired is not None
    assert capacities.usage_snapshot()["gpu:0"]["used"] == 1
    assert capacities.usage_snapshot()["nic:0"]["used"] == 1


def test_kv_reserve_commit_pin_release_lifecycle_and_capacity_backpressure():
    capacities = manager()
    reserved = capacities.reserve(("g", "producer"), "kv:0", 80)
    assert reserved is not None
    assert capacities.reserve(("g", "consumer"), "kv:0", 30) is None
    capacities.commit(reserved, "request-1")
    pin = capacities.pin(("g", "transfer"), "request-1")
    with pytest.raises(RuntimeError, match="pinned"):
        capacities.release(reserved, 1)
    capacities.unpin(pin, 2)
    assert capacities.release(reserved, 3) == (("g", "consumer"),)
    assert capacities.reserve(("g", "consumer"), "kv:0", 30) is not None


def test_kv_lifecycle_rejects_duplicate_commit_unpin_and_release():
    capacities = manager()
    reservation = capacities.reserve(("g", "producer"), "kv:0", 40)
    assert reservation is not None
    capacities.commit(reservation, "request-1")
    with pytest.raises(RuntimeError, match="already been committed"):
        capacities.commit(reservation, "request-2")
    pin = capacities.pin(("g", "transfer"), "request-1")
    capacities.unpin(pin, 1)
    with pytest.raises(RuntimeError, match="duplicate or unknown pin"):
        capacities.unpin(pin, 2)
    capacities.release(reservation, 3)
    with pytest.raises(RuntimeError, match="duplicate or unknown reservation"):
        capacities.release(reservation, 4)
    assert capacities.usage_snapshot()["kv:0"]["used"] == 0


def test_invalid_or_oversized_requests_do_not_change_capacity():
    capacities = manager()
    with pytest.raises(ValueError, match="exceeds capacity"):
        capacities.try_acquire(("g", "too-large"), (ResourceDemand("gpu:0", 2, "permits"),))
    with pytest.raises(ValueError, match="exceeds capacity"):
        capacities.reserve(("g", "too-large"), "kv:0", 101)
    assert all(value["used"] == 0 for value in capacities.usage_snapshot().values())


def test_resource_timeline_uses_executor_start_and_finish_times(graph_factory):
    graph = with_demands(graph_factory({"A": 2}), {
        "A": (ResourceDemand("gpu:0", 1, "permits"),),
    })
    runner = run(graph, manager())
    timeline = resource_timeline(runner.executor)
    assert len(timeline) == 1
    interval = timeline[0]
    assert (interval.resource_id, interval.start_s, interval.end_s) == ("gpu:0", 0, 2)


def test_capacity_trace_writes_resource_timeline_and_final_usage(graph_factory, tmp_path):
    graph = with_demands(graph_factory({"A": 2}), {
        "A": (ResourceDemand("gpu:0", 1, "permits"),),
    })
    runner = run(graph, manager())
    summary = write_results(tmp_path, runner)
    assert summary["resource_capacity_validated"] is True
    assert summary["resource_capacity"]["gpu:0"]["used"] == 0
    lines = (tmp_path / "resource_timeline.csv").read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("resource_id,unit")
    assert "gpu:0,permits,1,synthetic,A,0" in lines[1]


def test_failed_task_records_actual_release_interval_and_failed_report(graph_factory, tmp_path):
    from schemas.dag.v1.contracts import TaskState
    capacities = manager()
    graph = with_demands(graph_factory({"A": 10e-6}), {
        "A": (ResourceDemand("gpu:0", 1, "permits"),),
    })
    executor = DagExecutor(capacities, resource_units={"gpu:0": "permits"})
    initial = executor.submit(graph, 0, lambda *_: ()).initial_events
    executor.fail_task("synthetic", "A", 5e-6, "injected failure")
    intervals = resource_timeline(executor)
    assert len(intervals) == 1
    assert (intervals[0].start_s, intervals[0].end_s) == (0, 5e-6)
    task = executor.graphs["synthetic"].tasks["A"]
    assert task.state == TaskState.FAILED and task.end_at is None
    assert task.resource_released_at == 5e-6 and task.completion_count == 0
    assert capacities.usage_snapshot()["gpu:0"]["used"] == 0
    # Stale completion must neither release again nor extend the occupancy.
    for event in initial:
        assert executor.on_task_complete(*event.owner, event.time_s) == ()
    assert resource_timeline(executor) == intervals
    summary = write_results(tmp_path, DagRunner(executor))
    assert summary["status"] == "failed"
    assert summary["resource_capacity_validated"] is False
    assert summary["resource_capacity"]["gpu:0"]["used"] == 0
    import csv
    with (tmp_path / "resource_timeline.csv").open(encoding="utf-8", newline="") as stream:
        row, = list(csv.DictReader(stream))
    assert (float(row["start_at_s"]), float(row["end_at_s"])) == (0, 5e-6)


def test_unconfirmed_release_does_not_fabricate_resource_end_time(graph_factory, tmp_path):
    class BrokenRelease(CapacityResourceManager):
        def release(self, lease, now):
            raise RuntimeError("injected release error")
    capacities = BrokenRelease({"gpu:0": ResourceCapacity(1, "permits")})
    graph = with_demands(graph_factory({"A": 10e-6}), {
        "A": (ResourceDemand("gpu:0", 1, "permits"),),
    })
    executor = DagExecutor(capacities, resource_units={"gpu:0": "permits"})
    executor.submit(graph, 0, lambda *_: ())
    executor.fail_task("synthetic", "A", 5e-6, "injected failure")
    assert resource_timeline(executor) == ()
    assert executor.graphs["synthetic"].tasks["A"].resource_released_at is None
    summary = write_results(tmp_path, DagRunner(executor))
    assert summary["resource_capacity_validated"] is False
    assert summary["resource_capacity"]["gpu:0"]["used"] == 1
    assert summary["resource_capacity_check_errors"]


def test_graph_failure_cancels_only_its_waiters_and_keeps_other_graphs(graph_factory):
    capacities = manager()
    executor = DagExecutor(capacities, resource_units={"gpu:0": "permits"})
    demand = (ResourceDemand("gpu:0", 1, "permits"),)
    failed = with_demands(graph_factory({"A": 10e-6, "B": 4e-6}, graph_id="failed"),
                          {"A": demand, "B": demand})
    survivor = with_demands(graph_factory({"C": 1e-6}, graph_id="survivor"), {"C": demand})
    executor.submit(failed, 0, lambda *_: ())
    executor.submit(survivor, 0, lambda *_: ())
    executor.fail_task("failed", "A", 5e-6, "injected failure")
    # Acquiring and releasing unrelated work must never wake the failed graph.
    lease = capacities.try_acquire(("external", "task"), demand)
    assert lease is not None
    assert capacities.release(lease, 5e-6) == (("survivor", "C"),)
    intents = executor.dispatch(5e-6)
    assert len(intents) == 1 and intents[0].owner == ("survivor", "C")
    terminal_events = executor.on_task_complete(*intents[0].owner, intents[0].time_s)
    for event in terminal_events:
        executor.on_task_complete(*event.owner, event.time_s)
    assert executor.graphs["survivor"].state == "COMPLETED"
    assert capacities.usage_snapshot()["gpu:0"]["used"] == 0


def test_failed_graph_cancels_kv_waiters_without_freeing_external_reservation(graph_factory):
    capacities = manager()
    held = capacities.reserve(("external", "producer"), "kv:0", 80)
    assert capacities.reserve(("failed", "kv-waiter"), "kv:0", 30) is None
    assert capacities.reserve(("other", "kv-waiter"), "kv:0", 30) is None
    executor = DagExecutor(capacities)
    executor.submit(graph_factory({"A": 10e-6, "kv-waiter": 1e-6},
                                   (("A", "kv-waiter"),), graph_id="failed"), 0, lambda *_: ())
    executor.fail_task("failed", "A", 5e-6, "injected failure")
    assert capacities.usage_snapshot()["kv:0"]["used"] == 80
    assert capacities.release(held, 5e-6) == (("other", "kv-waiter"),)
