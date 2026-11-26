"""PD lifecycle and transfer graphs hosted by the original Simulator."""
from dataclasses import asdict
from math import ceil

from schemas.dag.v1.contracts import CostEstimate, GraphContext, GraphFragment, Placement, ResourceDemand, TaskSpec
from vidur.dag.executor import DagExecutor
from vidur.dag.kv_layout import KVLayout
from vidur.dag.pd_lifecycle import KVTransactions, Migration
from vidur.dag.resources import CapacityResourceManager, ResourceCapacity
from vidur.events.base_event import BaseEvent
from vidur.types import EventType


class PDActionEvent(BaseEvent):
    def __init__(self, coordinator, now, operation, request_id=None):
        super().__init__(now, EventType.DAG)
        self.coordinator, self.operation, self.request_id = coordinator, operation, request_id

    def handle_event(self, scheduler, metrics_store):
        if self.coordinator.failure:
            return []
        self.coordinator.now = self.time
        if self.operation == "commit":
            return self.coordinator.receive(self.request_id, self.time)
        if self.operation == "retry":
            return self.coordinator.retry(self.time)
        raise RuntimeError(f"unknown PD operation: {self.operation}")

    def to_dict(self):
        return dict(time=self.time, event_type="pd_"+self.operation, request_id=self.request_id)


class PDCoordinator:
    def __init__(self, scheduler, adapter, config, max_tokens):
        self.scheduler, self.adapter, self.config = scheduler, adapter, config
        self.now = 0.0
        self.failure = None
        self.migrations, self.requests = {}, {}
        self.waiting = {}  # Insertion order is stable across capacity retries.
        self.layouts = {}
        self.pull_groups = {}  # destination -> ordered migrations held by a receive step
        capacities = {key: ResourceCapacity(value["capacity"], value["unit"])
                      for key, value in adapter.executor._resources.usage_snapshot().items()}
        first = None
        for rid, rs in scheduler._replica_schedulers.items():
            replica = rs.replica
            if replica.pd_p2p_comm_dtype != config.storage_dtype:
                raise ValueError("PD storage dtype must match replica KV dtype")
            layout = KVLayout(replica.num_layers, replica.num_kv_heads, replica.attention_head_dim,
                replica._replica_config.tensor_parallel_size, replica.num_pipeline_stages,
                config.storage_dtype, rs._config.block_size)
            if config.transfer_start_mode == "decode_pull_candidate" and (layout.tp != 1 or layout.pp != 1):
                raise ValueError("candidate decode pull currently supports TP1 PP1 only")
            if config.legacy_prefill_billing_extra_token and (layout.tp != 1 or layout.pp != 1):
                raise ValueError("legacy fee parity is supported only for TP1 PP1")
            if first is not None and layout != first:
                raise ValueError("PD currently requires homogeneous P/D KV layouts")
            first = layout
            self.layouts[rid] = layout
            rs._max_blocks_per_sequence = ceil(max_tokens / layout.block_size)
            for gpu in layout.shards(rid):
                amount = min(config.capacity_bytes_per_shard,
                             rs._config.num_blocks * layout.block_size * layout.bytes_per_token_per_shard)
                capacities["kv:"+gpu] = ResourceCapacity(amount, "bytes")
            rs.pd_coordinator = self
        if adapter.executor.graphs:
            raise RuntimeError("PD resources must be initialized before submitting any graph")
        self.manager = CapacityResourceManager(capacities)
        adapter.executor = DagExecutor(self.manager, resource_units={key: value.unit for key, value in capacities.items()},
                                       ready_queue_policy=adapter.executor.ready_queue_policy)
        self.tx = KVTransactions(self.manager, first)

    def _ledger_allocate(self, rs, request, amount):
        if request.id in rs._allocation_map:
            raise RuntimeError("duplicate PD block allocation")
        rs.allocate(request.id, rs._max_blocks_per_sequence)
        total = amount * len(self.layouts[rs.replica_id].shards(rs.replica_id))
        rs.replica._kv_cache_allocation_map[request.id] = total
        rs.replica._allocated_kv_cache_memory += total

    def _ledger_release(self, rs, request):
        if request.id in rs._allocation_map:
            rs.free(request.id)
            rs.replica.release_request_kv_cache_memory(request)

    def ready(self, request, now):
        m = self.migrations.get(str(request.id))
        return bool(m and m.state in ("KV_READY", "DECODING") and m.kv_ready_at_s <= now
                    and m.destination_handles)

    def next_batch(self, rs):
        from vidur.entities import Batch
        from vidur.entities.replica import ReplicaType
        if self.failure:
            raise RuntimeError(self.failure)
        selected, tokens = [], []
        is_prefill = rs.replica.replica_type == ReplicaType.PREFILL
        if not is_prefill and rs.replica_id in self.pull_groups:
            return None  # Decode worker is busy pulling this receive batch.
        for request in tuple(rs._preempted_requests) + tuple(rs._request_queue):
            if request.completed or request in selected:
                continue
            count = request.num_prefill_tokens if is_prefill else 1
            if len(selected) >= min(rs._max_batch_size, rs._max_micro_batch_size):
                break
            if sum(tokens) + count > rs._config.max_tokens_in_batch:
                continue
            rid = str(request.id)
            if is_prefill:
                if rid in self.migrations:
                    raise RuntimeError("chunked/restarted Prefill is not supported by DAG PD")
                layout = self.layouts[rs.replica_id]
                storage = rs._max_blocks_per_sequence * layout.block_size * layout.bytes_per_token_per_shard
                if not rs.can_allocate(rs._max_blocks_per_sequence):
                    continue
                handles = self.tx.reserve(rid, rs.replica_id, storage, "source", self.now)
                if handles is None:
                    continue
                m = Migration(rid, rs.replica_id, request.decode_replica_id, storage,
                              layout.wire(request.num_prefill_tokens), source_handles=handles)
                self.migrations[rid], self.requests[rid] = m, request
                self.tx.commit(rid, handles, "source", self.now)
                self._ledger_allocate(rs, request, storage)
            else:
                if not self.ready(request, self.now):
                    continue
                m = self.migrations[rid]
                m.state = "DECODING"
            selected.append(request)
            tokens.append(count)
            for queue in (rs._preempted_requests, rs._request_queue):
                if request in queue:
                    queue.remove(request)
        return Batch(rs.replica_id, selected, tokens) if selected else None

    def on_stage_start(self, batch, replica_id, now):
        for request in batch.requests:
            m = self.migrations[str(request.id)]
            if replica_id == m.destination:
                if not self.ready(request, now):
                    raise RuntimeError("Decode Stage started before KVReady")
                if m.first_decode_start_s is None:
                    m.first_decode_start_s = now

    def on_batch_end(self, rs, batch):
        rs._num_running_batches -= 1
        from vidur.entities.replica import ReplicaType
        for request in batch.requests:
            m = self.migrations[str(request.id)]
            if request.completed:
                self.tx.unpin(m, self.now)
                self.tx.release(m.request_id, m.source_handles, self.now)
                self.tx.release(m.request_id, m.destination_handles, self.now)
                self._ledger_release(rs, request)
                m.state, m.completed_at_s = "COMPLETED", self.now
            elif rs.replica.replica_type == ReplicaType.PREFILL:
                if m.state != "PREFILL_RUNNING":
                    raise RuntimeError("duplicate PD Prefill completion")
                self.tx.pin(m, self.now)
                m.prefill_completed_at_s = self.now
                m.state = "WAITING_DESTINATION"
                self.waiting[m.request_id] = None
            else:
                rs._preempted_requests.append(request)

    def notifications(self, now):
        from vidur.events.replica_schedule_event import ReplicaScheduleEvent
        return [PDActionEvent(self, now, "retry")] + [ReplicaScheduleEvent(now, rid)
                    for rid in sorted(self.scheduler._replica_schedulers)]

    def retry(self, now):
        if self.config.transfer_start_mode == "decode_pull_candidate":
            return self._retry_decode_pull(now)
        events = []
        for rid in tuple(self.waiting):
            m, request = self.migrations[rid], self.requests[rid]
            rs = self.scheduler.get_replica_scheduler(m.destination)
            if not rs.can_allocate(rs._max_blocks_per_sequence):
                continue
            handles = self.tx.reserve(rid, m.destination, m.storage_bytes, "destination", now)
            if handles is None:
                continue
            m.destination_handles = handles
            self._ledger_allocate(rs, request, m.storage_bytes)
            m.destination_reserved_at_s, m.state = now, "TRANSFERRING"
            del self.waiting[rid]
            events.extend(self._submit_transfer(m, now))
        return events

    def _retry_decode_pull(self, now):
        """Candidate: a free Decode worker selects a batch and pulls KVs serially.

        No host launch, cache installation or sampling cost is inferred here. This
        is an opt-in scheduling diagnostic, not a validated vLLM timing model.
        """
        events = []
        destinations = dict.fromkeys(self.migrations[rid].destination for rid in self.waiting)
        for destination in destinations:
            rs = self.scheduler.get_replica_scheduler(destination)
            # A paused Decode batch must not prevent a pending receive step:
            # captured vLLM traces show receives between Decode forward steps.
            # Prior newly-ready requests retain priority until scheduled.
            if destination in self.pull_groups or rs._num_running_batches or rs._request_queue:
                continue
            selected, prefill_tokens = [], 0
            limit = min(rs._max_batch_size, rs._max_micro_batch_size)
            for rid in tuple(self.waiting):
                m, request = self.migrations[rid], self.requests[rid]
                if m.destination != destination or len(selected) >= limit:
                    continue
                if prefill_tokens + request.num_prefill_tokens > rs._config.max_tokens_in_batch:
                    break
                if not rs.can_allocate(rs._max_blocks_per_sequence):
                    break
                handles = self.tx.reserve(rid, destination, m.storage_bytes, "destination", now)
                if handles is None:
                    break
                m.destination_handles = handles
                self._ledger_allocate(rs, request, m.storage_bytes)
                m.destination_reserved_at_s, m.state = now, "PULL_QUEUED"
                del self.waiting[rid]
                selected.append(rid)
                prefill_tokens += request.num_prefill_tokens
            if selected:
                self.pull_groups[destination] = selected
                self.tx.record(now, "pull_batch_selected", ",".join(selected))
                first = self.migrations[selected[0]]
                first.state = "TRANSFERRING"
                events.extend(self._submit_transfer(first, now))
        return events

    def _submit_transfer(self, m, now):
        if m.graph_id is not None:
            raise RuntimeError("duplicate transfer submission")
        layout = self.layouts[m.source]
        tp = layout.tp
        m.graph_ids = [f"pd/{m.request_id}/stage{stage}/migration0" for stage in range(layout.pp)]
        m.graph_id = m.graph_ids[0]
        sources, destinations = layout.shards(m.source), layout.shards(m.destination)
        completed_graphs = set()
        def completed(gid, time):
            if gid in completed_graphs:
                raise RuntimeError("duplicate PD terminal")
            completed_graphs.add(gid)
            if len(completed_graphs) == len(m.graph_ids):
                self.adapter._outbox.append(PDActionEvent(self, time, "commit", m.request_id))
            return ()
        events = []
        for stage, gid in enumerate(m.graph_ids):
            tasks = []
            # Keep physical KV bytes distinct from the optional comparison fee.
            # The original SimAI baseline charges for prefill tokens plus one.
            billing_bytes = m.wire_bytes + (
                layout.bytes_per_token_per_shard
                if self.config.legacy_prefill_billing_extra_token else 0
            )
            duration = self.config.latency_s + billing_bytes / self.config.bandwidth_bytes_per_s
            for index, (source, destination) in enumerate(zip(sources[stage*tp:(stage+1)*tp], destinations[stage*tp:(stage+1)*tp])):
                endpoints = sorted({self.adapter.placement.endpoints[gpu] for gpu in (source, destination)})
                resources = sorted(set(endpoints + ([source, destination] if self.config.occupies_gpu else [])))
                metadata = dict(op="pd.transfer", communication_type="pd", payload_bytes=m.wire_bytes,
                    wire_bytes=m.wire_bytes, billing_bytes=billing_bytes,
                    billing_basis=("legacy_prefill_plus_one" if self.config.legacy_prefill_billing_extra_token else "valid_kv_tokens"),
                    storage_bytes=m.storage_bytes, source=source, destination=destination,
                    endpoints=endpoints, occupies_gpu=self.config.occupies_gpu, bandwidth_bytes_per_s=self.config.bandwidth_bytes_per_s,
                    latency_s=self.config.latency_s, evidence=self.config.evidence)
                tasks.append(TaskSpec(f"transfer.{index}", "comm", Placement((source, destination), gid),
                    tuple(ResourceDemand(resource, 1, "permits") for resource in resources),
                    CostEstimate(duration, ("pd.latency_plus_billing_over_bandwidth" if self.config.legacy_prefill_billing_extra_token
                                            else "pd.latency_plus_wire_over_bandwidth"), duration, "s", 1,
                                 self.config.evidence, ("pd",)), metadata))
            tasks.append(TaskSpec("terminal", "sync", Placement(), (),
                CostEstimate(0, "pd.join", 0, "s", 1, "all KV shards received", ("sync",))))
            graph = GraphFragment("1.0", gid, GraphContext(m.request_id, 0, str(m.source), stage, (m.request_id,)),
                tuple(tasks), tuple((t.task_id, "terminal") for t in tasks[:-1]), "terminal")
            event = PDActionEvent(self, now, "commit", m.request_id)
            self.adapter.graph_anchors[gid] = event.id
            handle = self.adapter.executor.submit(graph, now, completed)
            events.extend(self.adapter._wrap(handle.initial_events))
        return events

    def receive(self, rid, now):
        m = self.migrations[rid]
        if m.state != "TRANSFERRING":
            raise RuntimeError("duplicate or stale PD receive commit")
        graphs = [self.adapter.executor.graph_snapshot(gid) for gid in m.graph_ids]
        if any(graph.state != "COMPLETED" for graph in graphs):
            raise RuntimeError("cannot commit KV before every transfer completes")
        self.tx.commit(rid, m.destination_handles, "destination", now)
        self.tx.unpin(m, now)
        self.tx.release(rid, m.source_handles, now)
        request = self.requests[rid]
        self._ledger_release(self.scheduler.get_replica_scheduler(m.source), request)
        m.kv_ready_at_s, m.state = now, "KV_READY"
        request.decode_arrived_at = now
        destination = self.scheduler.get_replica_scheduler(m.destination)
        if self.config.transfer_start_mode == "push" and request not in destination._request_queue:
            destination._request_queue.append(request)
        request.pd_p2p_comm_size = m.wire_bytes * len(self.layouts[m.source].shards(m.source))
        request.pd_p2p_comm_bandwidth = self.config.bandwidth_bytes_per_s
        request.pd_p2p_comm_time = now - m.prefill_completed_at_s
        self.tx.record(now, "kv_ready", rid)
        if self.config.transfer_start_mode == "decode_pull_candidate":
            group = self.pull_groups[m.destination]
            next_rid = next((item for item in group if self.migrations[item].state == "PULL_QUEUED"), None)
            if next_rid is not None:
                following = self.migrations[next_rid]
                following.state = "TRANSFERRING"
                return self._submit_transfer(following, now)
            for item in group:
                queued = self.requests[item]
                if queued not in destination._request_queue:
                    destination._request_queue.append(queued)
            del self.pull_groups[m.destination]
        return self.notifications(now)

    def abort(self, now, reason):
        if self.failure:
            return
        self.failure = str(reason)
        self.waiting.clear()
        self.pull_groups.clear()
        for rid, m in self.migrations.items():
            if m.state == "COMPLETED":
                continue
            m.state = "FAILED"
            actions = [lambda: self.tx.unpin(m, now),
                       lambda: self.tx.release(rid, m.source_handles, now),
                       lambda: self.tx.release(rid, m.destination_handles, now)]
            for action in actions:
                try:
                    action()
                except Exception as exc:
                    self.tx.cleanup_errors.append(f"{rid}: {type(exc).__name__}: {exc}")
            request = self.requests[rid]
            for replica, handles in ((m.source, m.source_handles), (m.destination, m.destination_handles)):
                if not handles:
                    self._ledger_release(self.scheduler.get_replica_scheduler(replica), request)
            self.manager.cancel_waiters(((f"pd:{rid}", "source"), (f"pd:{rid}", "destination")))

    def assert_completed(self):
        if self.waiting or self.pull_groups or any(m.state != "COMPLETED" for m in self.migrations.values()):
            raise RuntimeError("PD stopped with unfinished migrations or capacity waiters")
        if any(m.source_handles or m.destination_handles or m.pins for m in self.migrations.values()):
            raise RuntimeError("PD completed with retained KV handles")

    def write_results(self, output):
        from pathlib import Path
        from vidur.utils.diagnostics import write_json_atomic
        from vidur.dag.expanded_trace import write_csv
        output = Path(output)
        rows = []
        graphs = self.adapter.executor.graphs
        for rid, m in self.migrations.items():
            row = {key: value for key, value in asdict(m).items()
                   if key not in ("source_handles", "destination_handles", "pins")}
            row.update(source_reservations=len(m.source_handles), destination_reservations=len(m.destination_handles), pins=len(m.pins))
            transfer_tasks = ([t for gid in m.graph_ids for t in graphs[gid].tasks.values()
                               if t.spec.kind == "comm"] if m.graph_id else [])
            starts = [t.start_at for t in transfer_tasks if t.start_at is not None]
            ends = [t.end_at for t in transfer_tasks if t.end_at is not None]
            row.update(transfer_started_at_s=min(starts) if starts else None,
                transfer_completed_at_s=max(ends) if len(ends) == len(transfer_tasks) and ends else None,
                capacity_wait_s=(m.destination_reserved_at_s-m.prefill_completed_at_s
                    if m.destination_reserved_at_s is not None else None),
                network_resource_wait_work_s=sum(t.resource_wait_s for t in transfer_tasks))
            rows.append(row)
        status = "failed" if self.failure else ("completed" if all(m.state == "COMPLETED" for m in self.migrations.values()) else "in_progress")
        write_json_atomic(output / "pd-summary.json", dict(status=status,
            migrations=rows, cleanup_errors=self.tx.cleanup_errors, config=asdict(self.config),
            resource_capacity=self.manager.usage_snapshot(), hardware_accuracy_claim=False))
        write_json_atomic(output / "kv-events.json", self.tx.events)
        capacity_rows = [dict(time_s=e["time_s"], operation=e["operation"], request_id=e["request_id"],
            resource_id=resource, **usage) for e in self.tx.events for resource, usage in e["usage"].items()
            if usage["unit"] == "bytes"]
        if capacity_rows:
            write_csv(output / "kv-capacity.csv", tuple(capacity_rows[0]), capacity_rows)
        if rows:
            write_csv(output / "pd-transfers.csv", tuple(rows[0]), rows)
