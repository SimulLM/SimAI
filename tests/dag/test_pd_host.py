from types import SimpleNamespace as NS
import heapq

import pytest

from vidur.dag.expanded import ExpandedDagAdapter
from vidur.dag.pd import PDConfig
from vidur.dag.pd_host import PDCoordinator, PDActionEvent
from vidur.entities import Request
from vidur.entities.replica import ReplicaType


class ReplicaScheduler:
    def __init__(self, rid, tp, pp):
        self.replica_id = rid
        self.replica = NS(num_layers=pp, num_kv_heads=tp, attention_head_dim=1,
            num_pipeline_stages=pp, pd_p2p_comm_dtype="float16",
            _replica_config=NS(tensor_parallel_size=tp),
            replica_type=ReplicaType.PREFILL if rid == 0 else ReplicaType.DECODE,
            _kv_cache_allocation_map={}, _allocated_kv_cache_memory=0)
        self.replica.release_request_kv_cache_memory = self.release_memory
        self._config = NS(block_size=1, num_blocks=1000, max_tokens_in_batch=100)
        self._allocation_map, self._request_queue, self._preempted_requests = {}, [], []
        self._num_allocated_blocks = 0
        self._max_batch_size = self._max_micro_batch_size = 4
        self._num_running_batches = 1

    def can_allocate(self, blocks):
        return self._num_allocated_blocks + blocks <= self._config.num_blocks

    def allocate(self, rid, blocks):
        self._allocation_map[rid] = blocks
        self._num_allocated_blocks += blocks

    def free(self, rid):
        self._num_allocated_blocks -= self._allocation_map.pop(rid)

    def release_memory(self, request):
        self.replica._allocated_kv_cache_memory -= self.replica._kv_cache_allocation_map.pop(request.id)


def setup(*, capacity=64, tp=1, pp=1, shared=True, occupies=False, ready_queue_policy="submission"):
    replicas = {rid: ReplicaScheduler(rid, tp, pp) for rid in (0, 1)}
    scheduler = NS(_replica_schedulers=replicas, get_replica_scheduler=replicas.__getitem__)
    endpoints = {f"gpu:{r}:{s}:{rank}": "shared" for r in (0, 1) for s in range(pp) for rank in range(tp)}
    host = ExpandedDagAdapter([(r, s) for r in (0, 1) for s in range(pp)], tp,
                              "vidur", "synthetic", dict(ready_queue_policy=ready_queue_policy,
                                                         **(dict(endpoints=endpoints) if shared else {})))
    config = PDConfig("float16", capacity, 4, 0, occupies, "synthetic 4 bytes/s")
    pd = PDCoordinator(scheduler, host, config, 8)
    scheduler.pd_coordinator = pd
    return pd, host, replicas


def prefill(pd, replicas, at=1):
    request = Request(0, 2, 3)
    request.decode_replica_id = 1
    replicas[0]._request_queue.append(request)
    batch = pd.next_batch(replicas[0])
    request.on_batch_schedule(0)
    request.on_batch_end(at, 2)
    pd.now = at
    pd.on_batch_end(replicas[0], batch)
    return request


def drain_transfer(events):
    queue = [(e._priority_number, e) for e in events]
    heapq.heapify(queue)
    while queue:
        _, e = heapq.heappop(queue)
        # Business scheduler events are deliberately left to original-CLI tests.
        if e.__class__.__name__ == "ReplicaScheduleEvent":
            continue
        for event in e.handle_event(None, None):
            heapq.heappush(queue, (event._priority_number, event))


@pytest.mark.parametrize("policy", ["submission", "fcfs"])
def test_transfer_gates_decode_and_retains_source(policy):
    pd, host, rs = setup(ready_queue_policy=policy)
    assert host.executor.ready_queue_policy == policy
    request = prefill(pd, rs)
    m = pd.migrations[str(request.id)]
    assert m.pins and rs[0]._allocation_map
    assert not pd.ready(request, 1)
    events = pd.retry(1)
    assert pd.next_batch(rs[1]) is None
    assert m.source_handles and m.destination_handles
    drain_transfer(events)
    assert m.kv_ready_at_s == 3  # 2 valid tokens * 4 bytes / 4 B/s
    assert not m.source_handles and not m.pins
    assert not rs[0]._allocation_map and pd.ready(request, 3)
    assert pd.next_batch(rs[1]).requests == [request]
    pd.on_stage_start(NS(requests=[request]), 1, 3)
    assert m.first_decode_start_s == 3
    with pytest.raises(RuntimeError, match="duplicate"):
        pd.receive(m.request_id, 3)
    pd.abort(3, "test cleanup")
    assert all(v["used"] == 0 for v in pd.manager.usage_snapshot().values())


@pytest.mark.parametrize("policy", ["submission", "fcfs"])
def test_destination_capacity_backpressure_and_wakeup(policy):
    pd, host, rs = setup(capacity=32, ready_queue_policy=policy)
    a = prefill(pd, rs)
    drain_transfer(pd.retry(1))
    b = prefill(pd, rs, at=4)
    assert pd.retry(4) == []
    ma, mb = (pd.migrations[str(r.id)] for r in (a, b))
    assert ma.state == "KV_READY" and mb.state == "WAITING_DESTINATION"
    assert ma.state == "KV_READY" and mb.pins
    a._completed = True
    pd.now = 5
    pd.on_batch_end(rs[1], NS(requests=[a]))
    drain_transfer(pd.retry(5))
    assert mb.kv_ready_at_s == 7
    pd.abort(7, "test cleanup")
    assert all(v["used"] == 0 for v in pd.manager.usage_snapshot().values())


@pytest.mark.parametrize("shared,total", [(True, 9), (False, 3)])
def test_all_shards_join_and_endpoint_contention(shared, total):
    pd, host, rs = setup(tp=2, pp=2, shared=shared)
    request = prefill(pd, rs)
    drain_transfer(pd.retry(1))
    assert pd.migrations[str(request.id)].kv_ready_at_s == total
    graph = host.executor.graphs[pd.migrations[str(request.id)].graph_id]
    assert graph.callback_count == 1 and len(graph.tasks) == 3
    assert len(pd.migrations[str(request.id)].graph_ids) == 2
    pd.abort(total, "cleanup")


def test_abort_waiter_and_active_transfer_is_idempotent():
    pd, host, rs = setup(capacity=64)
    a, b = prefill(pd, rs), prefill(pd, rs)
    events = pd.retry(1)
    host.abort(1.5, "injected failure")
    pd.abort(1.5, "injected failure")
    pd.abort(1.5, "repeat")
    assert not pd.waiting and not pd.tx.cleanup_errors
    assert all(v["used"] == 0 for v in pd.manager.usage_snapshot().values())
    assert all(not r._allocation_map for r in rs.values())
    assert PDActionEvent(pd, 2, "commit", str(a.id)).handle_event(None, None) == []


def test_source_capacity_retries_only_after_release():
    pd, host, rs = setup(capacity=32)
    a = prefill(pd, rs)
    b = Request(0, 2, 3)
    b.decode_replica_id = 1
    rs[0]._request_queue.append(b)
    assert pd.next_batch(rs[0]) is None
    assert str(b.id) not in pd.migrations
    drain_transfer(pd.retry(1))
    assert pd.next_batch(rs[0]).requests == [b]
    pd.abort(3, "cleanup")


def test_two_requests_other_schedule_cannot_consume_unready_decode():
    pd, host, rs = setup(capacity=64)
    a, b = prefill(pd, rs), prefill(pd, rs)
    events = pd.retry(1)
    # Even explicit queue insertion cannot bypass the state gate.
    rs[1]._request_queue.extend([a, b])
    pd.now = 1
    assert pd.next_batch(rs[1]) is None
    drain_transfer(events)
    m = pd.migrations[str(b.id)]
    pd.now = m.kv_ready_at_s
    batch = pd.next_batch(rs[1])
    assert {r.id for r in batch.requests} == {a.id, b.id}
    pd.abort(pd.now, "cleanup")


def test_receive_before_completion_rejected_and_abort_waiter():
    pd, host, rs = setup(capacity=32)
    a = prefill(pd, rs)
    events = pd.retry(1)
    with pytest.raises(RuntimeError, match="every transfer"):
        pd.receive(str(a.id), 1)
    drain_transfer(events)
    b = prefill(pd, rs, at=4)
    assert pd.retry(4) == []
    host.abort(4, "capacity waiter cancelled")
    pd.abort(4, "capacity waiter cancelled")
    assert not pd.waiting and not pd.tx.cleanup_errors
    assert all(v["used"] == 0 for v in pd.manager.usage_snapshot().values())


def test_receive_commit_failure_keeps_decode_blocked_then_cleans(monkeypatch):
    pd, host, rs = setup()
    request = prefill(pd, rs)
    events = pd.retry(1)
    original = pd.manager.commit
    def fail_destination(reservation, allocation_id):
        if ":destination:" in allocation_id:
            raise RuntimeError("injected receive commit failure")
        return original(reservation, allocation_id)
    monkeypatch.setattr(pd.manager, "commit", fail_destination)
    with pytest.raises(RuntimeError, match="injected receive"):
        drain_transfer(events)
    assert not pd.ready(request, 3)
    host.abort(3, "receive failed")
    pd.abort(3, "receive failed")
    assert all(v["used"] == 0 for v in pd.manager.usage_snapshot().values())


def test_cutoff_snapshot_retains_live_pin_and_storage(tmp_path):
    import json
    pd, host, rs = setup()
    request = prefill(pd, rs)
    pd.retry(1)  # Stop before consuming any transfer completion.
    pd.write_results(tmp_path)
    report = json.loads((tmp_path/"pd-summary.json").read_text(encoding="utf-8"))
    assert report["status"] == "in_progress" and report["migrations"][0]["pins"] == 1
    assert not pd.ready(request, 1)
    assert sum(v["used"] for v in report["resource_capacity"].values() if v["unit"]=="bytes") == 64
    host.abort(1, "cleanup")
    pd.abort(1, "cleanup")


@pytest.mark.parametrize("failure", [False, True])
def test_real_simulator_cutoff_or_abort_preserves_pd_semantics(tmp_path, failure):
    from test_phase4_boundaries import host as simulator_host
    pd, adapter, rs = setup()
    request = prefill(pd, rs)
    simulator = simulator_host(tmp_path, adapter, limit=1.5 if not failure else float("inf"))
    simulator._scheduler = pd.scheduler
    pd.scheduler.dag_adapter = adapter
    pd.scheduler.is_empty = lambda: True
    simulator._add_events(pd.retry(1))
    if failure:
        def fail(*_):
            raise RuntimeError("injected PD host failure")
        simulator._add_event(NS(time=1.5, _time=1.5, _event_type="injected",
            _priority_number=(1.5, -1, None), handle_event=fail))
        with pytest.raises(RuntimeError, match="injected PD"):
            simulator.run()
        assert not simulator._event_queue and pd.failure
        assert all(v["used"]==0 for v in pd.manager.usage_snapshot().values())
    else:
        simulator.run()
        assert simulator._time == 1.5 and simulator._event_queue
        assert pd.migrations[str(request.id)].pins and not pd.failure
        adapter.abort(1.5, "test cleanup")
        pd.abort(1.5, "test cleanup")
