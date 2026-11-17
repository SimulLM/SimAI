"""Dynamic MoE extension of the original Simulator's expanded Stage adapter.

Append happens while routing is RUNNING and its join is PENDING. The original
completion event then releases routing, making the newly appended tasks ready.
There is no second clock, executor, or GPU/NIC resource manager.
"""
from collections import Counter, defaultdict
from dataclasses import replace
import csv
import json
from pathlib import Path

from schemas.dag.v1.contracts import GraphAppend, Placement, ResourceDemand, TaskSpec
from schemas.dag.v1.io import finite_nonnegative
from vidur.dag.expanded import ExpandedDagAdapter
from vidur.dag.moe import MoeConfig


class DynamicMoeDagAdapter(ExpandedDagAdapter):
    def __init__(self, stage_keys, tp, backend, model, settings, moe, *, device=None):
        stage_keys = tuple(stage_keys)
        if tp != 1 or any(stage != 0 for _, stage in stage_keys):
            raise ValueError("dynamic MoE currently requires TP=1 and PP=1")
        super().__init__(stage_keys, tp, backend, model, settings)
        configs = moe if isinstance(moe, tuple) else (moe,)
        self.moes = tuple(m if isinstance(m, MoeConfig) else MoeConfig(m) for m in configs)
        if not self.moes or len({m.group for m in self.moes}) != len(self.moes):
            raise ValueError("MoE groups must be nonempty and uniquely named")
        self.moe = self.moes[0]  # Compatibility for existing single-group callers.
        self.moe_by_device = {}
        for config in self.moes:
            group = self.placement.ep_groups.get(config.group)
            if group is None or set(group["members"]) != set(config.experts.values()):
                raise ValueError("dynamic MoE requires an explicit EP group with an expert on every member")
            if set(group["members"]).intersection(self.moe_by_device):
                raise ValueError("MoE groups cannot overlap")
            self.moe_by_device.update((gpu, config) for gpu in group["members"])
            if backend != "aicb" and config.cost.mode != "synthetic":
                raise ValueError("dense-to-MoE replacement is a synthetic structural fixture only")
            if config.cost.mode == "profile":
                actual = dict(model=model, device=device, tp=tp, pp=1, ep=len(group["members"]))
                if any(config.scope.get(k) != v for k, v in actual.items()):
                    raise ValueError("expert profile scope does not match runtime model/device/TP/PP/EP")
        if set(self.moe_by_device) != set(self.placement.endpoints):
            raise ValueError("MoE groups must cover all configured GPUs exactly once")
        self._iterations = Counter()
        self._pending_routes = {}
        self.rounds = []

    def validate_pd_groups(self, replica_roles):
        """EP membership stays within a P or D domain; PD moves KV between them."""
        roles = {gpu: replica_roles[replica] for (replica, _), devices in self.placement.devices.items()
                 for gpu in devices}
        for config in self.moes:
            if len({roles[gpu] for gpu in config.experts.values()}) != 1:
                raise ValueError("joint PD+MoE EP groups must stay within Prefill or Decode replicas")

    def _validate_initial_service(self, uncalibrated_service, batch_stage):
        # The removed aggregate is replaced, not added to the final dynamic cost.
        # ExpandedDagAdapter settles against the entire final graph at StageEnd.
        pass

    @staticmethod
    def _task(task_id, kind, devices, resources, cost, metadata, group=None):
        return TaskSpec(task_id, kind, Placement(tuple(devices), group),
                        tuple(ResourceDemand(r, 1, "permits") for r in sorted(set(resources))),
                        cost, metadata)

    def _build_fragment(self, graph_id, context, execution_time, is_last_stage, batch):
        if batch.num_prefill_tokens and batch.num_decode_tokens:
            raise ValueError("dynamic MoE requires separate prefill/decode batches; mixed phase costs are unvalidated")
        # pandas iterrows in the original trace replayer promotes integer counts
        # to floats. Normalize only whole, losslessly represented runtime counts;
        # JSON top-k, trace token IDs and payload fields remain strict integers.
        token_count = finite_nonnegative(batch.total_num_tokens)
        if not token_count.is_integer() or token_count != batch.total_num_tokens:
            raise ValueError("runtime token count must be a losslessly represented whole number")
        original = super()._build_fragment(graph_id, context, execution_time, is_last_stage, batch)
        iteration = self._iterations[context.replica_id]
        phase = "prefill" if batch.num_prefill_tokens else "decode"
        if self.backend == "aicb" and execution_time.expanded_aicb_profile()[1] != phase:
            raise ValueError("AICB layer profile phase does not match the routing batch phase")
        active_layers = {task.metadata["layer"] for task in original.tasks
                         if task.metadata["op"] in ("moe.compute", "moe.ep") and task.cost.duration_s > 0}
        if self.backend == "aicb" and not active_layers:
            raise ValueError("AICB profile contains no active MoE layer to expand")
        origin, = self.placement.devices[context.replica_id, context.stage_id]
        moe = self.moe_by_device[origin]
        tokens = {d: int(token_count) if d == origin else 0
                  for d in sorted(set(moe.experts.values()))}
        replacements, tasks = {}, []
        for task in original.tasks:
            op = task.metadata["op"]
            active = self.backend != "aicb" or task.metadata["layer"] in active_layers
            if op == "moe.ep" and self.backend == "aicb" and active:
                replacements[task.task_id] = ()
            elif active and op == ("moe.compute" if self.backend == "aicb" else "mlp.compute"):
                layer = task.metadata["layer"]
                prefix = f"layer{layer}.moe"
                route_id, join_id = prefix + ".route", prefix + ".join"
                metadata = dict(op="moe.route", layer=layer, iteration=iteration, phase=phase,
                                group=moe.group, cost_mode=moe.cost.mode, structural_fixture=self.backend != "aicb")
                tasks.append(self._task(route_id, "compute", (origin,), (origin,),
                                        moe.cost.routing(), metadata))
                tasks.append(self._task(join_id, "sync", (), (),
                                        moe.cost.estimate(0, "moe_join", "sync"),
                                        dict(op="moe.join", layer=layer, iteration=iteration)))
                replacements[task.task_id] = (route_id, join_id)
                self._pending_routes[graph_id, route_id] = (iteration, layer, phase, tokens, join_id, moe)
            else:
                tasks.append(task)
                replacements[task.task_id] = (task.task_id,)
        # The base builder is a linear Stage chain. Preserve all non-MoE tasks,
        # inserting a routing barrier and join at each original MoE position.
        chain = [name for task in original.tasks for name in replacements[task.task_id]]
        edges = tuple(zip(chain, chain[1:]))
        self._iterations[context.replica_id] += 1
        return replace(original, tasks=tuple(tasks), edges=edges)

    def _expand(self, graph_id, route_id, pending):
        iteration, layer, phase, tokens, join_id, moe = pending
        routing = moe.routing_result(tokens, iteration=iteration, layer=layer, phase=phase)
        digest = routing.digest
        matrix = routing.matrix(moe.experts)
        prefix = route_id.removesuffix(".route")
        bandwidth = self.placement.ep_groups[moe.group]["bandwidth_bytes_per_s"][phase]
        tasks, edges = [], set()
        dispatch, combine = {}, {}

        def transfer(source, target, count, direction):
            payload = count * (moe.cost.dispatch_bytes if direction == "dispatch" else moe.cost.combine_bytes)
            task_id = f"{prefix}.{direction}.{source}>{target}"
            metadata = dict(op="moe." + direction, layer=layer, iteration=iteration, phase=phase,
                            routing_digest=digest, source_device=source, destination_device=target,
                            assignments=count, payload_bytes=payload, bandwidth_bytes_per_s=bandwidth,
                            bandwidth_evidence=self.placement.ep_groups[moe.group]["evidence"])
            placement, resources = self.placement.communication(
                "ep", moe.group, (source, target), metadata)
            tasks.append(self._task(task_id, "comm", placement.device_ids, resources,
                                    moe.cost.transfer(payload, bandwidth), metadata, moe.group))
            return task_id

        for source, row in matrix.items():
            for target, count in row.items():
                if source != target and count:
                    dispatch[source, target] = transfer(source, target, count, "dispatch")
                    combine[target, source] = transfer(target, source, count, "combine")
                    edges.add((route_id, dispatch[source, target]))
                    edges.add((combine[target, source], join_id))

        counts = routing.expert_counts
        down_ids = {}
        expert_sources = defaultdict(set)
        for assignment in routing.assignments:
            expert_sources[assignment.expert].add(assignment.source)
        for expert in sorted(moe.experts):
            count = counts[expert]
            if not count:
                continue  # No-load experts do not consume an artificial minimum cost.
            device = moe.experts[expert]
            ids = {op: f"{prefix}.expert.{expert}.{op}" for op in ("up", "down")}
            down_ids[expert] = ids["down"]
            for op, task_id in ids.items():
                cost = moe.cost.expert(expert, phase, count, op)
                tasks.append(self._task(task_id, "compute", (device,), (device,), cost,
                                        dict(op="expert." + op, expert=expert, assignments=count,
                                             routing_digest=digest, layer=layer, iteration=iteration,
                                             phase=phase, group=moe.group, cost_mode=moe.cost.mode)))
            edges.add((route_id, ids["up"]))
            edges.add((ids["up"], ids["down"]))
            for source in expert_sources[expert]:
                if source == device:
                    edges.add((ids["down"], join_id))
                else:
                    edges.add((dispatch[source, device], ids["up"]))
                    edges.add((ids["down"], combine[device, source]))
        return GraphAppend(graph_id, tuple(tasks), tuple(sorted(edges))), dict(
            graph_id=graph_id, route_task_id=route_id, join_task_id=join_id,
            routing_digest=digest, routing=routing.to_dict(), matrix=matrix,
            expert_counts={e: counts[e] for e in sorted(moe.experts)},
            expert_down_tasks=down_ids, cost_mode=moe.cost.mode, group=moe.group,
            expert_devices=dict(moe.experts), dispatch_bytes_per_assignment=moe.cost.dispatch_bytes,
            combine_bytes_per_assignment=moe.cost.combine_bytes,
            structural_fixture=self.backend != "aicb")

    def handle(self, intent):
        if self.failure:
            return []
        owner = intent.owner
        if intent.kind != "task_complete" or owner not in self._pending_routes:
            return super().handle(intent)
        try:
            task = self.executor.graph_snapshot(owner[0]).tasks[owner[1]]
            if task.state != "RUNNING" or task.scheduled_finish_at != intent.time_s:
                raise RuntimeError("routing expansion requires its matching RUNNING completion")
            patch, record = self._expand(*owner, self._pending_routes[owner])
            # Freeze and validate the complete patch atomically, before releasing
            # routing. The existing route->join edge cannot make join ready early.
            appended = self.executor.append(patch, intent.time_s)
            self.rounds.append(record)
            del self._pending_routes[owner]
            events = self._wrap(appended)
            return events + super().handle(intent)
        except Exception as exc:
            self.abort(intent.time_s, str(exc))
            raise

    def write_moe_results(self, output):
        output = Path(output)
        loads, matrices, rounds = [], [], []
        graphs = self.executor.graphs
        for record in self.rounds:
            graph = graphs[record["graph_id"]]
            routing = record["routing"]
            identity = dict(graph_id=record["graph_id"], group=record["group"], iteration=routing["iteration"],
                            layer=routing["layer"], phase=routing["phase"],
                            strategy=routing["strategy"], routing_digest=record["routing_digest"])
            for expert, count in record["expert_counts"].items():
                task_id = record["expert_down_tasks"].get(expert)
                down = graph.tasks[task_id] if task_id else None
                up = graph.tasks[task_id.removesuffix(".down") + ".up"] if task_id else None
                loads.append(dict(**identity, expert=expert, device=record["expert_devices"][expert], assignments=count,
                                  up_start_s=up.start_at if up else None, down_end_s=down.end_at if down else None,
                                  compute_service_s=up.spec.cost.duration_s + down.spec.cost.duration_s if up else 0,
                                  resource_wait_s=up.resource_wait_s + down.resource_wait_s if up else 0))
            for source, row in record["matrix"].items():
                for target, count in row.items():
                    matrices.append(dict(**identity, source=source, destination=target, assignments=count,
                                         dispatch_wire_bytes=count * record["dispatch_bytes_per_assignment"] if source != target else 0,
                                         combine_wire_bytes=count * record["combine_bytes_per_assignment"] if source != target else 0))
            ends = [graph.tasks[t].end_at for t in record["expert_down_tasks"].values()]
            finished = [t for t in ends if t is not None]
            route_task, join = graph.tasks[record["route_task_id"]], graph.tasks[record["join_task_id"]]
            rounds.append(dict(**identity, cost_mode=record["cost_mode"], graph_state=graph.state,
                               assignment_count=len(routing["assignments"]),
                               route_end_s=route_task.end_at, join_end_s=join.end_at,
                               expert_tail_span_s=max(finished) - min(finished) if finished else None))
        chrome_events = []
        for gid, graph in graphs.items():
            for task in graph.tasks.values():
                if task.start_at is None or task.end_at is None:
                    continue
                spec = task.spec
                lane = ",".join(spec.placement.device_ids) or "cpu/sync"
                chrome_events.append(dict(name=spec.task_id, cat=spec.kind, ph="X", pid=gid, tid=lane,
                                          ts=task.start_at * 1e6, dur=(task.end_at - task.start_at) * 1e6,
                                          args=dict(spec.metadata, resource_wait_s=task.resource_wait_s,
                                                    cost_source=spec.cost.source)))
        (output / "moe-task-chrome.json").write_text(json.dumps(
            dict(traceEvents=chrome_events, displayTimeUnit="ms"), allow_nan=False) + "\n", encoding="utf-8")
        (output / "moe-routing.json").write_text(json.dumps(
            dict(schema_version="1.0", accuracy_status="blocked_missing_matched_reference",
                 rounds=self.rounds), indent=2, allow_nan=False) + "\n", encoding="utf-8")
        for name, rows in (("moe-expert-loads.csv", loads), ("moe-communication-matrix.csv", matrices),
                           ("moe-rounds.csv", rounds)):
            with (output / name).open("w", encoding="utf-8", newline="") as stream:
                if rows:
                    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
                    writer.writeheader()
                    writer.writerows(rows)
