"""Ready-time arbitration: no overtaking, stable ties, no unrelated blocking."""
from dataclasses import replace

import pytest

from schemas.dag.v1.contracts import GraphAppend, ResourceDemand
from vidur.dag.executor import DagExecutor
from vidur.dag.expanded import ExpandedDagAdapter
from vidur.dag.resources import CapacityResourceManager, ResourceCapacity
from vidur.dag.runner import DagRunner


def runner(policy):
    manager = CapacityResourceManager({"link:shared": ResourceCapacity(1, "permits")})
    return DagRunner(DagExecutor(manager, resource_units={"link:shared": "permits"},
                                 ready_queue_policy=policy))


def graph(factory, name, prepare, transfer):
    fragment = factory({"prepare": prepare, "transfer": transfer},
                       (("prepare", "transfer"),), graph_id=name)
    return replace(fragment, tasks=tuple(replace(t, kind="comm", demands=(
        ResourceDemand("link:shared", 1, "permits"),)) if t.task_id == "transfer" else t
        for t in fragment.tasks))


@pytest.mark.parametrize("policy,order", [("submission", ["busy", "late", "early"]),
                                          ("fcfs", ["busy", "early", "late"])])
def test_resource_waiter_keeps_original_ready_time_across_retries(graph_factory, policy, order):
    run = runner(policy)
    # 'late' is submitted first, but 'early' reaches the busy link first.
    for name, prepare, transfer in (("busy", 0, 5), ("late", 3, 1), ("early", 2, 1)):
        run.submit(graph(graph_factory, name, prepare, transfer))
    assert run.run() == 7
    observed = sorted(order, key=lambda name: run.executor.graphs[name].tasks["transfer"].start_at)
    assert observed == order
    early = run.executor.graphs["early"].tasks["transfer"]
    assert early.ready_at == 2
    assert early.resource_wait_s == (3 if policy == "fcfs" else 4)
    assert all(t.completion_count == 1 for g in run.executor.graphs.values() for t in g.tasks.values())
    assert all(v["used"] == 0 for v in run.executor._resources.usage_snapshot().values())


def test_fcfs_equal_ready_times_use_submission_order(graph_factory):
    run = runner("fcfs")
    for name, prepare in (("busy", 0), ("first", 2), ("second", 2)):
        run.submit(graph(graph_factory, name, prepare, 5 if name == "busy" else 1))
    run.run()
    assert run.executor.graphs["first"].tasks["transfer"].start_at == 5
    assert run.executor.graphs["second"].tasks["transfer"].start_at == 6


def test_fcfs_does_not_block_unrelated_resources_or_preempt(graph_factory):
    run = runner("fcfs")
    run.submit(graph(graph_factory, "busy", 0, 5))
    run.submit(graph(graph_factory, "waiting", 1, 1))
    run.submit(graph_factory({"independent": 2}, graph_id="free"))
    run.run()
    assert run.executor.graphs["free"].tasks["independent"].end_at == 2
    assert run.executor.graphs["busy"].tasks["transfer"].end_at == 5
    assert run.executor.graphs["waiting"].tasks["transfer"].start_at == 5


def test_fcfs_dynamic_append_uses_readiness_not_old_graph_submission(graph_factory):
    run = runner("fcfs")
    run.submit(graph_factory({"hold_join": 10}, graph_id="old"))
    run.submit(graph(graph_factory, "busy", 0, 5))
    run.submit(graph(graph_factory, "waiting", 1, 1))
    while run.now < 1:
        run.step()
    task = graph(graph_factory, "unused", 0, 1).tasks[1]
    run.append(GraphAppend("old", (replace(task, task_id="appended"),),
                           (("appended", "terminal"),)), now=2)
    run.run()
    assert run.executor.graphs["waiting"].tasks["transfer"].start_at == 5
    assert run.executor.graphs["old"].tasks["appended"].start_at == 6


@pytest.mark.parametrize("policy", ["fcfs", "submission"])
def test_expanded_adapter_propagates_selected_policy(policy):
    host = ExpandedDagAdapter([(0, 0)], 1, "vidur", "dense", {"ready_queue_policy": policy})
    assert host.executor.ready_queue_policy == policy


def test_default_compatibility_and_invalid_policy():
    assert DagExecutor().ready_queue_policy == "submission"
    assert ExpandedDagAdapter([(0, 0)], 1, "vidur", "dense", {}).executor.ready_queue_policy == "submission"
    with pytest.raises(ValueError, match="ready_queue_policy"):
        DagExecutor(ready_queue_policy="shortest_job")
    with pytest.raises(ValueError, match="ready_queue_policy"):
        ExpandedDagAdapter([(0, 0)], 1, "vidur", "dense", {"ready_queue_policy": "shortest_job"})
