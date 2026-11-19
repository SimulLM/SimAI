"""PD and MoE share one host clock and resource manager across P/D EP groups."""
import json
from types import SimpleNamespace as NS

import pytest

from vidur.dag.moe import load_config
from vidur.dag.moe_host import DynamicMoeDagAdapter
from vidur.dag.pd import PDConfig
from vidur.dag.pd_host import PDCoordinator
from vidur.entities import BatchStage
from test_coarse_host import drain
from test_dynamic_moe import config
from test_expanded_stage import snapshot
from test_pd_host import ReplicaScheduler, drain_transfer, prefill


def joint_configs():
    configs = []
    groups = {}
    for role, ranks in (("prefill", (0, 1)), ("decode", (2, 3))):
        data = config(["balanced", "hotspot"])
        data["group"] = role
        devices = [f"gpu:{rank}:0:0" for rank in ranks]
        data["experts"] = {f"e{i}": devices[i // 2] for i in range(4)}
        configs.append(data)
        groups[role] = dict(members=devices, bandwidth_bytes_per_s=dict(prefill=1e6, decode=1e6),
                            evidence="synthetic joint unit test")
    return configs, dict(ep_groups=groups, endpoints={f"gpu:{i}:0:0": "shared" for i in range(4)})


def make_host(configs=None, *, ready_queue_policy="submission"):
    data, resources = joint_configs()
    resources["ready_queue_policy"] = ready_queue_policy
    return DynamicMoeDagAdapter([(i, 0) for i in range(4)], 1, "vidur", "dense", resources,
                                tuple(configs or data))


def test_load_multiple_groups_and_reject_missing_or_duplicate_members(tmp_path):
    configs, _ = joint_configs()
    path = tmp_path / "groups.json"
    path.write_text(json.dumps(dict(schema_version="1.0", groups=configs)))
    assert len(load_config(path)) == 2
    make_host(load_config(path))
    with pytest.raises(ValueError, match="uniquely named"):
        make_host([configs[0], configs[0]])
    with pytest.raises(ValueError, match="cover all"):
        make_host([configs[0]])


def test_joint_ep_groups_cannot_cross_prefill_decode_boundary():
    host = make_host()
    host.validate_pd_groups({str(i): "P" if i < 2 else "D" for i in range(4)})
    with pytest.raises(ValueError, match="stay within"):
        host.validate_pd_groups({str(i): "P" if i % 2 == 0 else "D" for i in range(4)})


@pytest.mark.parametrize("policy", ["submission", "fcfs"])
def test_transfer_then_dynamic_decode_and_final_kv_cleanup(tmp_path, policy):
    from vidur.entities.replica import ReplicaType
    replicas = {rid: ReplicaScheduler(rid, 1, 1) for rid in range(4)}
    for rid, rs in replicas.items():
        rs.replica.replica_type = ReplicaType.PREFILL if rid < 2 else ReplicaType.DECODE
    scheduler = NS(_replica_schedulers=replicas, get_replica_scheduler=replicas.__getitem__)
    host = make_host(ready_queue_policy=policy)
    pd = PDCoordinator(scheduler, host, PDConfig("float16", 64, 4, 0, True, "synthetic"), 8)
    assert host.executor.ready_queue_policy == policy
    scheduler.pd_coordinator = pd
    request = prefill(pd, replicas)
    # The helper chooses destination 1; put the request on an actual D rank.
    migration = pd.migrations[str(request.id)]
    migration.destination = request.decode_replica_id = 2
    assert pd.manager is host.executor._resources
    drain_transfer(pd.retry(1))
    ready = migration.kv_ready_at_s
    assert ready == 3 and not migration.pins and not migration.source_handles
    pd.now = ready
    batch = pd.next_batch(replicas[2])
    stage = BatchStage(batch.id, 2, 0, 0, 0, batch.requests, batch.num_tokens)
    record = {}
    def start(now):
        pd.on_stage_start(batch, 2, now)
        stage.on_schedule(now)
    end, = drain(host.submit_stage(ready, 2, 0, True, batch, stage,
        on_stage_start=start, execution_time=snapshot(), record=record))
    assert migration.first_decode_start_s >= ready
    assert host.rounds[0]["group"] == "decode"
    graph = host.executor.graph_snapshot(record["graph_id"])
    assert all(set(task.spec.placement.device_ids).issubset({"gpu:2:0:0", "gpu:3:0:0"})
               for task in graph.tasks.values() if task.spec.metadata.get("op", "").startswith("expert."))
    stage.on_stage_end(end.time)
    request._completed = True
    pd.now = end.time
    pd.on_batch_end(replicas[2], batch)
    pd.assert_completed()
    host.assert_completed()
    assert all(value["used"] == 0 for value in pd.manager.usage_snapshot().values())
    host.write_moe_results(tmp_path)
    exported = json.loads((tmp_path / "moe-routing.json").read_text())
    assert exported["rounds"][0]["expert_devices"]["e0"] == "gpu:2:0:0"


def test_group_selection_keeps_prefill_and_decode_routes_separate():
    from test_dynamic_moe import submit
    host = make_host()
    first, = drain(submit(host, replica=0)[0])
    drain(submit(host, replica=2, now=first.time, phase="decode")[0])
    assert [record["group"] for record in host.rounds] == ["prefill", "decode"]
    for record in host.rounds:
        expected = {"gpu:0:0:0", "gpu:1:0:0"} if record["group"] == "prefill" else {"gpu:2:0:0", "gpu:3:0:0"}
        assert set(record["matrix"]) == expected


def test_one_snapshot_per_graph_export_instead_of_per_layer(monkeypatch, tmp_path):
    from test_dynamic_moe import submit
    host = make_host()
    drain(submit(host, execution_time=snapshot(num_layers=3))[0])
    def no_per_round_copy(*_):
        raise AssertionError("export should reuse one detached graph dictionary")
    monkeypatch.setattr(host.executor, "graph_snapshot", no_per_round_copy)
    host.write_moe_results(tmp_path)
    assert len(json.loads((tmp_path / "moe-routing.json").read_text())["rounds"]) == 3


def test_joint_host_failure_releases_decode_kv_and_all_task_leases(tmp_path, monkeypatch):
    from vidur.entities.replica import ReplicaType
    from test_phase4_boundaries import host as simulator_host
    replicas = {rid: ReplicaScheduler(rid, 1, 1) for rid in range(4)}
    for rid, rs in replicas.items():
        rs.replica.replica_type = ReplicaType.PREFILL if rid < 2 else ReplicaType.DECODE
    scheduler = NS(_replica_schedulers=replicas, get_replica_scheduler=replicas.__getitem__, is_empty=lambda: True)
    host = make_host()
    pd = PDCoordinator(scheduler, host, PDConfig("float16", 64, 4, 0, True, "synthetic"), 8)
    scheduler.pd_coordinator, scheduler.dag_adapter = pd, host
    request = prefill(pd, replicas)
    migration = pd.migrations[str(request.id)]
    migration.destination = request.decode_replica_id = 2
    drain_transfer(pd.retry(1))
    pd.now = 3
    batch = pd.next_batch(replicas[2])
    stage = BatchStage(batch.id, 2, 0, 0, 0, batch.requests, batch.num_tokens)
    events = host.submit_stage(3, 2, 0, True, batch, stage, on_stage_start=stage.on_schedule,
                               execution_time=snapshot())
    def failed_expansion(*_):
        raise RuntimeError("injected joint routing failure")
    monkeypatch.setattr(host, "_expand", failed_expansion)
    simulator = simulator_host(tmp_path, host)
    simulator._time = 3
    simulator._scheduler = scheduler
    simulator._requests = [request]
    simulator._add_events(events)
    with pytest.raises(RuntimeError, match="joint routing failure"):
        simulator.run()
    assert pd.failure and not simulator._event_queue
    assert not migration.destination_handles and not migration.source_handles and not migration.pins
    assert all(v["used"] == 0 for v in pd.manager.usage_snapshot().values())
