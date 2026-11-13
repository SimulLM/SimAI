"""Phase 5 regressions for expanded cost, endpoint contention and real StageEnd."""
from dataclasses import replace
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from schemas.dag.v1.contracts import GraphAppend, GraphContext, Placement, ResourceDemand
from vidur.dag.expanded import ATTENTION, CPU_POST, CPU_PRE, MLP, ExpandedDagAdapter, ExpandedStageBuilder
from vidur.dag.expanded_trace import write_expanded_results
from vidur.dag.runner import DagRunner
from vidur.dag.trace import write_results
from vidur.entities import BatchStage, Request
from vidur.events.replica_stage_schedule_event import ReplicaStageScheduleEvent
from vidur.scheduler.replica_stage_scheduler.replica_stage_schduler import ReplicaStageScheduler

from test_coarse_host import drain


def save_probe(name, runner):
    if root := os.environ.get("PHASE5_PROBE_OUTPUT"):
        output = Path(root) / name
        output.mkdir(parents=True, exist_ok=False)
        write_results(output, runner)
        write_expanded_results(output, runner.executor)


def snapshot(**overrides):
    values = dict.fromkeys((*ATTENTION, *MLP, *CPU_PRE, *CPU_POST, "add_time",
                           "attention_all_reduce_time", "mlp_all_reduce_time",
                           "pipeline_parallel_communication_time"), 0)
    values.update(num_layers=1, total_time=0, model_time=0)
    values.update(overrides)
    return SimpleNamespace(**values)


def test_appended_expert_is_charged_at_stage_end():
    adapter = ExpandedDagAdapter([(0, 0)], 1, "vidur", "dense", {})
    request = Request(0, 8, 4)
    request.on_batch_schedule(0)
    batch = SimpleNamespace(id=1, requests=[request])
    stage = BatchStage(1, 0, 0, 1e-3, 1e-3, [request], [8])
    record = {}
    events = adapter.submit_stage(
        0, 0, 0, True, batch, stage, on_stage_start=stage.on_schedule,
        execution_time=snapshot(attention_pre_proj_time=1, total_time=1e-3), record=record,
    )
    graph_id = record["graph_id"]
    compute = adapter.executor.graph_snapshot(graph_id).tasks["layer0.attention.compute"].spec
    expert = replace(compute, task_id="expert", cost=replace(compute.cost, duration_s=2e-3, raw_value=2))
    patch = GraphAppend(graph_id, (expert,), ((compute.task_id, expert.task_id), (expert.task_id, "terminal")))
    events.extend(adapter._wrap(adapter.executor.append(patch, 0)))
    end, = drain(events)
    stage.on_stage_end(end.time)

    graph = adapter.executor.graph_snapshot(graph_id)
    assert sum(task.cost.duration_s for task in graph.fragment.tasks) == pytest.approx(3e-3)
    assert graph.callback_count == 1
    assert stage.execution_time == pytest.approx(3e-3)
    assert stage.model_execution_time == pytest.approx(3e-3)
    assert request.model_execution_time == pytest.approx(3e-3)
    assert record["expanded_service_s"] == pytest.approx(3e-3)


def ep_probe(phase="prefill"):
    adapter = ExpandedDagAdapter(
        [(0, 0), (1, 0)], 1, "aicb", "deepseek-671B",
        {"ep_groups": {"experts": {
            "members": ["gpu:0:0:0", "gpu:1:0:0"],
            "bandwidth_bytes_per_s": {"prefill": 1e6, "decode": 2e6},
            "evidence": "synthetic unit and bandwidth fixture",
        }}},
    )
    layer = {op: {"comp_time": 1000} for op in ("attention", "mlp", "moe")}
    layer["moe"]["comm_size"] = 4
    cost = snapshot(expanded_aicb_profile=lambda: ({0: layer}, phase, 2), total_time=7e-9, model_time=7e-9)
    return adapter, cost


@pytest.mark.parametrize(("phase", "seconds"), [("prefill", 7e-6), ("decode", 5e-6)])
def test_ep_runs_through_original_stage_and_corrects_units(phase, seconds):
    adapter, cost = ep_probe(phase)
    request = Request(0, 8, 4)
    request.on_batch_schedule(0)
    batch = SimpleNamespace(id=1, requests=[request], request_ids=[request.id], num_tokens=[8])
    calls = []

    def predict(*_):
        calls.append(1)
        return cost

    stage = ReplicaStageScheduler(0, 0, True, SimpleNamespace(get_execution_time=predict))
    stage.add_batch(batch)
    scheduler = SimpleNamespace(_replica_schedulers={0: SimpleNamespace(_replica_stage_schedulers={0: stage})},
                                get_replica_stage_scheduler=lambda *_: stage, dag_adapter=adapter,
                                stage_execution_records=[])
    metrics = SimpleNamespace(on_replica_stage_schedule=lambda *_: None, on_batch_stage_end=lambda *_: None)
    events = ReplicaStageScheduleEvent(0, 0, 0).handle_event(scheduler, metrics)
    end, = drain(events)
    end.handle_event(scheduler, metrics)
    graph, = adapter.executor.graphs.values()
    ep = graph.tasks["layer0.moe.ep"].spec
    assert ep.metadata["payload_bytes"] == 4
    assert ep.metadata["phase"] == phase and ep.placement.comm_group == "experts"
    assert {d.resource_id for d in ep.demands} == {
        "gpu:0:0:0", "gpu:1:0:0", "link:gpu:0:0:0", "link:gpu:1:0:0",
    }
    assert calls == [1] and graph.callback_count == 1 and not stage._is_busy
    assert request.execution_time == pytest.approx(seconds)
    assert scheduler.stage_execution_records[0]["predicted_duration_s"] == 7e-9
    adapter.now = end.time
    save_probe(f"ep-{phase}", adapter)


@pytest.mark.parametrize(("independent", "expected"), [(True, 10e-3), (False, 14e-3)])
def test_compute_and_pp_overlap_only_with_independent_resources(independent, expected):
    settings = {"independent_comm": ["pp"]} if independent else {}
    adapter = ExpandedDagAdapter([(0, 0), (0, 1)], 1, "vidur", "dense", settings)
    context = GraphContext("test", 0, "0", 0, ("request",))
    cost = snapshot(attention_pre_proj_time=10, pipeline_parallel_communication_time=4)
    serial = ExpandedStageBuilder("controlled", cost, adapter.placement, "vidur", False,
                                  payload_bytes=8192).build(context)
    by_id = {task.task_id: task for task in serial.tasks}
    compute = by_id["layer0.attention.compute"]
    transfer = by_id["pipeline.send_recv"]
    # Put the compute on the PP receive device so the default transfer must wait.
    compute = replace(compute, placement=Placement(("gpu:0:1:0",)),
                      demands=(ResourceDemand("gpu:0:1:0", 1, "permits"),))
    terminal = by_id["terminal"]
    fragment = replace(serial, tasks=(compute, transfer, terminal),
                       edges=((compute.task_id, "terminal"), (transfer.task_id, "terminal")))
    runner = DagRunner(adapter.executor)
    runner.submit(fragment)
    assert runner.run() == pytest.approx(expected)
    graph, = runner.executor.graphs.values()
    pp = graph.tasks[transfer.task_id]
    assert pp.resource_wait_s == pytest.approx(0 if independent else 10e-3)
    assert graph.callback_count == 1
    assert all(r["used"] == 0 for r in runner.executor._resources.usage_snapshot().values())
    save_probe("independent-pp" if independent else "shared-pp-receiver", runner)


def test_invalid_subcomponent_cannot_hide_inside_aggregate():
    adapter = ExpandedDagAdapter([(0, 0)], 1, "vidur", "dense", {})
    cost = snapshot(attention_pre_proj_time=1, attention_post_proj_time=-1)
    builder = ExpandedStageBuilder("invalid", cost, adapter.placement, "vidur", True)
    with pytest.raises(ValueError, match="finite nonnegative"):
        builder.build(GraphContext("batch", 0, "0", 0, ()))


@pytest.mark.parametrize(("tp", "stages"), [(2, [(0, 0)]), (1, [(0, 0), (0, 1)])])
def test_aicb_rejects_unpriced_tp_and_unsupported_pp(tp, stages):
    with pytest.raises(ValueError, match="PP=1 and TP=1"):
        ExpandedDagAdapter(stages, tp, "aicb", "deepseek-671B", {})
