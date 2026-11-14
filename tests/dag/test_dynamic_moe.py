"""Phase-7 conservation, dynamic barriers, resource contention and settlement."""
from copy import deepcopy
from collections import defaultdict
from hashlib import sha256
import json
from types import SimpleNamespace

import pytest
import numpy as np

from schemas.dag.v1.contracts import ResourceDemand
from vidur.dag.moe import MoeConfig, route
from vidur.dag.moe_host import DynamicMoeDagAdapter
from vidur.entities import BatchStage, Request

from test_coarse_host import drain
from test_expanded_stage import snapshot

GPU0, GPU1 = "gpu:0:0:0", "gpu:1:0:0"
EXPERTS = {"e0": GPU0, "e1": GPU0, "e2": GPU1, "e3": GPU1}


def config(patterns=None):
    return dict(schema_version="1.0", group="experts", experts=EXPERTS,
                routing=dict(top_k=2, patterns=patterns or ["balanced"], seed=0),
                cost=dict(mode="synthetic", evidence="Synthetic test only; seconds and bytes",
                          route_s=1e-6, up_s_per_assignment=1e-3, down_s_per_assignment=1e-3,
                          dispatch_bytes_per_assignment=8, combine_bytes_per_assignment=8, latency_s=0))


def settings(independent=True):
    return dict(independent_comm=["ep"] if independent else [], ep_groups=dict(experts=dict(
        members=[GPU0, GPU1], bandwidth_bytes_per_s=dict(prefill=1e9, decode=1e9),
        evidence="Synthetic logical link, not measured bandwidth")))


def adapter(data=None, *, independent=True, backend="vidur", model="dense"):
    return DynamicMoeDagAdapter([(0, 0), (1, 0)], 1, backend, model,
                                settings(independent), data or config(), device="a100")


def submit(host, *, replica=0, now=0, tokens=8, execution_time=None, phase="prefill"):
    request = Request(now, tokens, 4)
    request.on_batch_schedule(now)
    batch = SimpleNamespace(id=len(host.stage_ends), requests=[request], total_num_tokens=tokens,
                            num_prefill_tokens=tokens if phase == "prefill" else 0,
                            num_decode_tokens=tokens if phase == "decode" else 0)
    stage = BatchStage(batch.id, replica, 0, 0, 0, [request], [tokens])
    record = {}
    events = host.submit_stage(now, replica, 0, True, batch, stage, on_stage_start=stage.on_schedule,
                               execution_time=execution_time or snapshot(), record=record)
    return events, stage, request, record


@pytest.mark.parametrize("strategy", ["balanced", "hotspot"])
@pytest.mark.parametrize("top_k", [1, 2, 4])
def test_complete_multisource_matrix_and_conservation(strategy, top_k):
    result = route({GPU0: 7, GPU1: 3}, EXPERTS, top_k=top_k, iteration=2,
                   layer=0, phase="decode", strategy=strategy)
    assert len(result.assignments) == 10 * top_k
    assert sum(result.expert_counts.values()) == 10 * top_k
    matrix = result.matrix(EXPERTS)
    assert set(matrix) == {GPU0, GPU1} and all(set(row) == {GPU0, GPU1} for row in matrix.values())
    assert sum(matrix[GPU0].values()) == 7 * top_k
    assert sum(matrix[GPU1].values()) == 3 * top_k
    assert result.digest == result.digest


def test_same_destination_counts_do_not_define_source_destination_matrix():
    def routed(first, second):
        return route({GPU0: 1, GPU1: 1}, EXPERTS, top_k=1, iteration=0, layer=0, phase="prefill",
                     strategy="trace", trace=[dict(source=GPU0, token=0, experts=[first]),
                                              dict(source=GPU1, token=0, experts=[second])])
    local, remote = routed("e0", "e2"), routed("e2", "e0")
    assert local.expert_counts == remote.expert_counts
    assert local.matrix(EXPERTS) != remote.matrix(EXPERTS)
    assert local.digest != remote.digest


def test_trace_replay_numpy_token_counts_are_normalized_without_rounding():
    result = route({GPU0: np.int64(3), GPU1: np.int64(0)}, EXPERTS, top_k=2,
                   iteration=0, layer=0, phase="decode")
    assert len(result.assignments) == 6
    assert json.loads(json.dumps(result.to_dict()))["tokens_by_source"][GPU0] == 3
    assert len(result.digest) == 64


def test_original_batch_whole_float_tokens_are_normalized_at_host_boundary():
    host = adapter()
    drain(submit(host, tokens=np.float64(3.0), phase="decode")[0])
    assert len(host.rounds[0]["routing"]["assignments"]) == 6
    with pytest.raises(ValueError, match="whole number"):
        submit(host, tokens=3.5, now=host.now)


@pytest.mark.parametrize("trace", [[], [dict(source=GPU0, token=0, experts=["e0", "e0"])],
                                    [dict(source=GPU0, token=0, experts=["e0", "unknown"])],
                                    [dict(source=GPU1, token=0, experts=["e0", "e1"])]])
def test_missing_duplicate_or_unknown_assignments_fail(trace):
    with pytest.raises(ValueError):
        route({GPU0: 1}, EXPERTS, top_k=2, iteration=0, layer=0, phase="decode", strategy="trace", trace=trace)


def test_route_appends_before_join_and_settles_final_cost_once(tmp_path):
    host = adapter()
    events, stage, request, record = submit(host, execution_time=snapshot(schedule_time=2))
    graph = host.executor.graph_snapshot(record["graph_id"])
    assert not any(".expert." in name for name in graph.tasks)
    assert graph.tasks["layer0.moe.join"].state == "PENDING"
    end, = drain(events)
    stage.on_stage_end(end.time)
    graph = host.executor.graph_snapshot(record["graph_id"])
    assert graph.callback_count == 1 and len(host.rounds) == 1
    assert graph.tasks["layer0.moe.join"].start_at >= max(
        task.end_at for task in graph.tasks.values() if task.spec.metadata.get("op") in
        ("expert.down", "moe.combine"))
    assert stage.execution_time == pytest.approx(end.time)
    assert stage.model_execution_time == pytest.approx(sum(
        t.spec.cost.duration_s for t in graph.tasks.values() if not t.spec.task_id.startswith("cpu.")))
    assert request.model_execution_time == pytest.approx(stage.model_execution_time)
    assert record["expanded_service_s"] == pytest.approx(sum(t.spec.cost.duration_s for t in graph.tasks.values()))
    assert stage.model_execution_time < record["expanded_service_s"]
    for expert in EXPERTS:
        up, down = [graph.tasks[f"layer0.moe.expert.{expert}.{op}"].spec for op in ("up", "down")]
        assert up.metadata["routing_digest"] == down.metadata["routing_digest"] == host.rounds[0]["routing_digest"]
        assert up.metadata["assignments"] == down.metadata["assignments"] == 4
    host.write_moe_results(tmp_path)
    assert len(json.loads((tmp_path / "moe-routing.json").read_text())["rounds"]) == 1
    assert len((tmp_path / "moe-communication-matrix.csv").read_text().splitlines()) == 5
    assert all(v["used"] == 0 for v in host.executor._resources.usage_snapshot().values())


def test_same_gpu_queues_different_gpus_overlap_and_hotspot_has_tail():
    balanced = adapter()
    end, = drain(submit(balanced)[0])
    graph, = balanced.executor.graphs.values()
    expert_tasks = [t for t in graph.tasks.values() if t.spec.metadata.get("op", "").startswith("expert.")]
    same_card_wait = sum(t.resource_wait_s for t in expert_tasks)
    assert same_card_wait > 0
    for gpu in (GPU0, GPU1):
        tasks = sorted((t for t in expert_tasks if t.spec.placement.device_ids == (gpu,)), key=lambda t: t.start_at)
        assert all(a.end_at <= b.start_at for a, b in zip(tasks, tasks[1:]))
    assert any(a.start_at < b.end_at and b.start_at < a.end_at for a in expert_tasks for b in expert_tasks
               if a.spec.placement != b.spec.placement)
    hotspot = adapter(config(["hotspot"]))
    hot_end, = drain(submit(hotspot)[0])
    assert hot_end.time > end.time * 1.9
    hot_graph, = hotspot.executor.graphs.values()
    assert not any(".expert.e2." in name or ".expert.e3." in name for name in hot_graph.tasks)
    assert hotspot.rounds[0]["expert_counts"] == dict(e0=8, e1=8, e2=0, e3=0)


def test_external_gpu_ownership_delays_experts_and_join():
    host = adapter()
    held = host.executor._resources.try_acquire(("external", "busy"), (ResourceDemand(GPU1, 1, "permits"),))
    events, _, _, record = submit(host)
    assert drain(events) == []  # local branch finishes; remote branch and join still wait
    graph = host.executor.graph_snapshot(record["graph_id"])
    assert graph.tasks["layer0.moe.join"].state == "PENDING" and graph.callback_count == 0
    host.executor._resources.release(held, 1)
    end, = drain(host._wrap(host.executor.dispatch(1)))
    assert end.time > 1
    assert host.executor.graph_snapshot(record["graph_id"]).callback_count == 1


def test_multiround_and_replica_routing_identity_is_local():
    host = adapter(config(["balanced", "hotspot"]))
    first, = drain(submit(host)[0])
    second, = drain(submit(host, now=first.time, phase="decode", tokens=3)[0])
    drain(submit(host, replica=1, now=second.time)[0])
    assert [r["routing"]["iteration"] for r in host.rounds] == [0, 1, 0]
    assert [r["routing"]["strategy"] for r in host.rounds] == ["balanced", "hotspot", "balanced"]
    assert len({r["routing_digest"] for r in host.rounds}) == 3
    assert all(g.callback_count == 1 for g in host.executor.graphs.values())


def test_two_live_graphs_share_expert_and_nic_capacity():
    host = adapter(independent=False)
    first = submit(host, replica=0)[0]
    second = submit(host, replica=1)[0]
    assert len(drain(first + second)) == 2
    intervals = defaultdict(list)
    for graph in host.executor.graphs.values():
        for task in graph.tasks.values():
            if task.end_at > task.start_at:
                for demand in task.spec.demands:
                    intervals[demand.resource_id].append((task.start_at, task.end_at))
    for entries in intervals.values():
        entries.sort()
        assert all(a[1] <= b[0] for a, b in zip(entries, entries[1:]))
    assert any(t.resource_wait_s > 0 for g in host.executor.graphs.values() for t in g.tasks.values())
    assert all(v["used"] == 0 for v in host.executor._resources.usage_snapshot().values())


def test_independent_ep_still_waits_for_shared_nic():
    resources = settings(independent=True)
    resources["endpoints"] = {GPU0: "shared", GPU1: "shared"}
    host = DynamicMoeDagAdapter([(0, 0), (1, 0)], 1, "vidur", "dense", resources, config())
    initial = submit(host)[0] + submit(host, replica=1)[0]
    assert len(drain(initial)) == 2
    transfers = [t for g in host.executor.graphs.values() for t in g.tasks.values() if t.spec.kind == "comm"]
    assert any(t.resource_wait_s > 0 for t in transfers)
    assert all({d.resource_id for d in t.spec.demands} == {"link:shared"} for t in transfers)


def test_aicb_aggregate_replaced_without_double_charging():
    host = adapter(backend="aicb", model="deepseek-671B")
    layer = {op: dict(comp_time=1000) for op in ("attention", "mlp", "moe")}
    layer["moe"].update(comp_time=1e12, comm_size=1e12)
    execution_time = snapshot(expanded_aicb_profile=lambda: ({0: layer}, "prefill", 2))
    _, stage, _, record = run = submit(host, execution_time=execution_time)
    end, = drain(run[0])
    graph = host.executor.graph_snapshot(record["graph_id"])
    assert "layer0.moe.compute" not in graph.tasks and "layer0.moe.ep" not in graph.tasks
    assert "layer0.mlp.compute" in graph.tasks  # AICB's separate dense/shared MLP remains.
    assert end.time < 1 and stage.model_execution_time < 1


def test_zero_moe_profile_layer_keeps_dense_work_without_inserting_experts():
    host = adapter(backend="aicb", model="deepseek-671B")
    dense = dict(attention=dict(comp_time=1000), mlp=dict(comp_time=1000), moe=dict(comp_time=0, comm_size=0))
    sparse = deepcopy(dense)
    sparse["moe"] = dict(comp_time=1000, comm_size=4)
    events, _, _, record = submit(host, execution_time=snapshot(num_layers=2,
        expanded_aicb_profile=lambda: ({0: dense, 1: sparse}, "prefill", 2)))
    drain(events)
    graph = host.executor.graph_snapshot(record["graph_id"])
    assert "layer0.moe.route" not in graph.tasks and "layer0.mlp.compute" in graph.tasks
    assert "layer1.moe.route" in graph.tasks and "layer1.moe.compute" not in graph.tasks
    assert [record["routing"]["layer"] for record in host.rounds] == [1]


def test_all_zero_moe_profile_fails_instead_of_claiming_dynamic_execution():
    host = adapter(backend="aicb", model="deepseek-671B")
    layer = dict(attention=dict(comp_time=1000), mlp=dict(comp_time=1000), moe=dict(comp_time=0, comm_size=0))
    with pytest.raises(ValueError, match="no active MoE"):
        submit(host, execution_time=snapshot(expanded_aicb_profile=lambda: ({0: layer}, "prefill", 2)))
    assert not host.executor.graphs


def profile_config(tmp_path):
    data = config()
    data["scope"] = dict(model="deepseek-671B", device="a100", tp=1, pp=1, ep=2, dtype="fp16")
    evidence = tmp_path / "estimated.json"
    evidence.write_text('{"nature":"estimated","purpose":"unit test only"}')
    records = [dict(expert=expert, phase="prefill", assignments=4, up_s=.001, down_s=.002,
                    scope=data["scope"], nature="estimated", evidence=[dict(path=str(evidence),
                    sha256=sha256(evidence.read_bytes()).hexdigest())]) for expert in EXPERTS]
    data["cost"].pop("up_s_per_assignment")
    data["cost"].pop("down_s_per_assignment")
    data["cost"].update(mode="profile", profiles=records)
    return data


def test_exact_expert_profiles_and_evidence_are_required(tmp_path):
    data = profile_config(tmp_path)
    costs = MoeConfig(data).cost
    assert costs.expert("e0", "prefill", 4, "down").duration_s == .002
    assert costs.expert("e0", "prefill", 4, "up").source == "expert_profile:estimated"
    with pytest.raises(ValueError, match="no exact"):
        costs.expert("e0", "prefill", 5, "up")
    with pytest.raises(ValueError, match="no exact"):
        costs.expert("e0", "decode", 4, "up")
    altered = deepcopy(data)
    altered["cost"]["profiles"][0]["scope"] = dict(data["scope"], ep=3)
    with pytest.raises(ValueError, match="scope"):
        MoeConfig(altered)
    altered = deepcopy(data)
    altered["scope"]["dtype"] = []
    with pytest.raises(ValueError, match="complete"):
        MoeConfig(altered)
    data["cost"]["profiles"][0]["evidence"][0]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="hash"):
        MoeConfig(data)


def test_missing_profile_aborts_before_partial_append_and_releases_resources(tmp_path):
    data = profile_config(tmp_path)
    data["cost"]["profiles"] = data["cost"]["profiles"][:1]
    host = adapter(data, backend="aicb", model="deepseek-671B")
    layer = {op: dict(comp_time=1000) for op in ("attention", "mlp", "moe")}
    layer["moe"]["comm_size"] = 4
    execution_time = snapshot(expanded_aicb_profile=lambda: ({0: layer}, "prefill", 2))
    events, _, _, record = submit(host, execution_time=execution_time)
    with pytest.raises(ValueError, match="no exact"):
        drain(events)
    graph = host.executor.graph_snapshot(record["graph_id"])
    assert graph.state == "FAILED" and graph.callback_count == 0 and not host.rounds
    assert not any(".expert." in name for name in graph.tasks)
    assert all(v["used"] == 0 for v in host.executor._resources.usage_snapshot().values())


def test_profile_mode_runs_with_exact_matching_loads(tmp_path):
    host = adapter(profile_config(tmp_path), backend="aicb", model="deepseek-671B")
    layer = {op: dict(comp_time=1000) for op in ("attention", "mlp", "moe")}
    layer["moe"]["comm_size"] = 4
    events, _, _, record = submit(host, execution_time=snapshot(
        expanded_aicb_profile=lambda: ({0: layer}, "prefill", 2)))
    drain(events)
    graph = host.executor.graph_snapshot(record["graph_id"])
    assert graph.callback_count == 1
    assert all(t.spec.cost.source == "expert_profile:estimated" for t in graph.tasks.values()
               if t.spec.metadata.get("op", "").startswith("expert."))


def test_multiple_layers_expand_sequentially_with_unique_join_barriers():
    host = adapter()
    end, = drain(submit(host, execution_time=snapshot(num_layers=2))[0])
    graph, = host.executor.graphs.values()
    assert len(host.rounds) == 2 and end.time > 0
    assert graph.tasks["layer1.moe.route"].start_at >= graph.tasks["layer0.moe.join"].end_at
    assert all(graph.tasks[f"layer{i}.moe.join"].completion_count == 1 for i in (0, 1))


@pytest.mark.parametrize("tp,keys", [(2, [(0, 0), (1, 0)]), (1, [(0, 0), (0, 1)])])
def test_unpriced_tp_or_pp_fail_before_execution(tp, keys):
    with pytest.raises(ValueError, match="TP=1 and PP=1"):
        DynamicMoeDagAdapter(keys, tp, "vidur", "dense", settings(), config())


def test_foreign_ep_placement_and_mixed_batches_fail():
    data = config()
    data["experts"] = {"e0": GPU0}
    data["routing"]["top_k"] = 1
    with pytest.raises(ValueError, match="expert on every member"):
        adapter(data)
    host = adapter()
    request = Request(0, 8, 4)
    batch = SimpleNamespace(id=1, requests=[request], num_prefill_tokens=8, num_decode_tokens=1)
    with pytest.raises(ValueError, match="separate prefill/decode"):
        host.submit_stage(0, 0, 0, True, batch, SimpleNamespace(execution_time=0), execution_time=snapshot())


def test_recorded_profile_scope_must_match_runtime(tmp_path):
    data = profile_config(tmp_path)
    data["scope"]["device"] = "h100"
    for record in data["cost"]["profiles"]:
        record["scope"] = data["scope"]
    with pytest.raises(ValueError, match="runtime"):
        adapter(data, backend="aicb", model="deepseek-671B")


def test_missing_routing_trace_fails_instead_of_reusing_previous_round():
    data = config(["trace"])
    data["routing"]["traces"] = [[]]
    with pytest.raises(ValueError, match="missing routing trace"):
        MoeConfig(data).routing_result({GPU0: 0}, iteration=1, layer=0, phase="decode")
