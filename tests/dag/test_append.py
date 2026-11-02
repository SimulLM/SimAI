from dataclasses import replace

import pytest

from schemas.dag.v1.contracts import GraphAppend, ResourceDemand, TaskState
from vidur.dag.executor import DagExecutor
from vidur.dag.runner import DagRunner


def extra(graph_factory, duration=3):
    return graph_factory({"X": duration}).tasks[0]


def test_append_before_pending_barrier_delays_join(graph_factory):
    runner = DagRunner()
    runner.submit(graph_factory({"A": 2, "B": 1}, (("A", "B"),)))
    patch = GraphAppend("synthetic", (extra(graph_factory),), (("A", "X"), ("X", "B")))
    assert runner.append(patch) == ()
    assert runner.run() == 6
    tasks = runner.executor.graphs["synthetic"].tasks
    assert (tasks["X"].start_at, tasks["X"].end_at) == (2, 5)
    assert tasks["B"].start_at == 5
    assert all(t.completion_count == 1 for t in tasks.values())


def test_append_completed_source_is_already_satisfied(graph_factory):
    runner = DagRunner()
    runner.submit(graph_factory({"A": 1, "Slow": 4, "B": 1},
                               (("A", "B"), ("Slow", "B"))))
    runner.step()  # A completes; B and terminal remain PENDING.
    patch = GraphAppend("synthetic", (extra(graph_factory, 2),), (("A", "X"), ("X", "B")))
    events = runner.append(patch)
    assert [(e.owner[1], e.time_s) for e in events] == [("X", 3)]
    assert runner.run() == 5
    assert runner.executor.graphs["synthetic"].tasks["B"].start_at == 4


def test_append_can_add_new_root_and_snapshot_metadata(graph_factory):
    runner = DagRunner()
    runner.submit(graph_factory({"A": 2, "B": 1}, (("A", "B"),)))
    metadata = {"routing": [1]}
    task = replace(extra(graph_factory), metadata=metadata)
    events = runner.append(GraphAppend("synthetic", (task,), (("X", "B"),)))
    assert events[0].owner == ("synthetic", "X")
    metadata["routing"].append(2)
    runner.run()
    assert runner.executor.graphs["synthetic"].tasks["X"].spec.metadata == {"routing": [1]}


@pytest.mark.parametrize("case", ["duplicate_task", "duplicate_edge", "missing_reference", "cycle",
                                 "running_target", "unjoined", "bad_cost", "bad_resource"])
def test_invalid_patch_is_atomic(graph_factory, case):
    executor = DagExecutor()
    runner = DagRunner(executor)
    runner.submit(graph_factory({"A": 2, "B": 1}, (("A", "B"),)))
    task = extra(graph_factory)
    edges = (("A", "X"), ("X", "B"))
    if case == "duplicate_task": task = replace(task, task_id="A")
    elif case == "duplicate_edge": edges += (("A", "B"),)
    elif case == "missing_reference": edges += (("missing", "X"),)
    elif case == "cycle": edges += (("B", "X"),)
    elif case == "running_target": edges = (("X", "A"),)
    elif case == "unjoined": edges = (("A", "X"),)
    elif case == "bad_cost": task = replace(task, cost=replace(task.cost, duration_s=-1))
    elif case == "bad_resource": task = replace(task, demands=(ResourceDemand("unknown", 1, "permits"),))
    before = executor.graphs
    with pytest.raises(ValueError):
        executor.append(GraphAppend("synthetic", (task,), edges), 1)
    assert executor.graphs == before and executor.now == 0
    assert runner.run() == 3  # Original queue and graph are still usable.


def test_ready_terminal_and_ready_target_rejected(graph_factory):
    executor = DagExecutor()
    executor.submit(graph_factory({}), 0, lambda *_: ())  # terminal is RUNNING
    with pytest.raises(ValueError, match="PENDING terminal"):
        executor.append(GraphAppend("synthetic", (), ()), 0)
    # READY task blocked by a resource manager is not a legal append target.
    from vidur.dag.testing import DependencyOnlyResources
    manager = DependencyOnlyResources()
    manager.blocked.add(("synthetic", "B"))
    other = DagExecutor(manager)
    other.submit(graph_factory({"A": 2, "B": 1}), 0, lambda *_: ())
    assert other.graphs["synthetic"].tasks["B"].state == TaskState.READY
    with pytest.raises(ValueError, match="target must be PENDING"):
        other.append(GraphAppend("synthetic", (extra(graph_factory),), (("X", "B"),)), 0)


def test_unknown_and_completed_graphs_reject_append(graph_factory):
    runner = DagRunner()
    with pytest.raises(ValueError, match="unknown graph"):
        runner.append(GraphAppend("missing", (), ()))
    runner.submit(graph_factory({}))
    runner.run()
    with pytest.raises(ValueError, match="PENDING terminal"):
        runner.append(GraphAppend("synthetic", (), ()))
