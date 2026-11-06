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
