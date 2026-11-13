"""Stage-level cost adaptation and logical device/communication placement."""
from math import fsum, isclose

from schemas.dag.v1.contracts import (
    CostEstimate, GraphFragment, Placement, ResourceDemand, TaskSpec,
)
from schemas.dag.v1.io import finite_nonnegative
from vidur.dag.host import CoarseDagAdapter

ATTENTION = (
    "attn_norm_time", "attention_pre_proj_time", "attention_rope_execution_time",
    "attention_kv_cache_save_execution_time", "attention_prefill_execution_time",
    "attention_decode_execution_time", "attention_post_proj_time",
)
MLP = (
    "mlp_norm_time", "mlp_layer_up_proj_execution_time",
    "mlp_layer_act_execution_time", "mlp_layer_down_proj_execution_time",
)
CPU_PRE = ("schedule_time", "prepare_inputs_e2e_time")
CPU_POST = ("sampler_e2e_time", "process_model_outputs_time", "ray_comm_time")
AICB_MODELS = {"deepseek-671B", "qwen3-moe-235B", "qwen3-next-80B"}
DENSE_BACKENDS = {"vidur", "simai_simulation", "simai_analytical"}


class StagePlacement:
    """One permit per GPU, replica CPU and configured communication endpoint."""

    def __init__(self, stage_keys, tp, settings):
        if not isinstance(settings, dict):
            raise ValueError("expanded DAG resource configuration must be an object")
        self.tp = tp
        self.devices = {
            (str(replica), stage): tuple(f"gpu:{replica}:{stage}:{rank}" for rank in range(tp))
            for replica, stage in stage_keys
        }
        devices = {device for stage in self.devices.values() for device in stage}
        if set(settings) - {"endpoints", "independent_comm", "ep_groups", "tp_cost_calibration"}:
            raise ValueError("unknown expanded DAG resource configuration field")
        endpoints = settings.get("endpoints", {})
        if (not isinstance(endpoints, dict) or set(endpoints) - devices or
                any(not isinstance(v, str) or not v for v in endpoints.values())):
            raise ValueError("endpoint mapping must name known GPUs and nonempty endpoint names")
        self.endpoints = {device: "link:" + endpoints.get(device, device) for device in devices}
        self.topology = "configured_endpoints" if set(endpoints) == devices else "logical_endpoints"
        independent = settings.get("independent_comm", [])
        if not isinstance(independent, list) or any(kind not in ("tp", "pp", "ep") for kind in independent):
            raise ValueError("independent_comm must list tp, pp or ep")
        self.independent = set(independent)
        self.ep_groups = settings.get("ep_groups", {})
        if not isinstance(self.ep_groups, dict):
            raise ValueError("ep_groups must map group names to member and bandwidth objects")
        assigned = set()
        for group, data in self.ep_groups.items():
            if not isinstance(data, dict):
                raise ValueError("EP group must be an object")
            members = data.get("members")
            if (not group or not isinstance(members, list) or not members or
                    any(not isinstance(member, str) for member in members) or
                    len(set(members)) != len(members) or set(members) - devices or assigned.intersection(members)):
                raise ValueError("EP groups require explicit, disjoint lists of known GPUs")
            assigned.update(members)
            bandwidth = data.get("bandwidth_bytes_per_s")
            evidence = data.get("evidence")
            if (not isinstance(bandwidth, dict) or set(bandwidth) != {"prefill", "decode"} or any(
                    finite_nonnegative(v) == 0 for v in bandwidth.values()) or
                    not isinstance(evidence, str) or not evidence.strip()):
                raise ValueError("EP requires positive phase bandwidth in bytes/s and evidence")
        self.resources = devices | set(self.endpoints.values()) | {
            f"cpu:{replica}" for replica, _ in self.devices
        }

    def communication(self, kind, group, devices, metadata):
        endpoints = tuple(sorted({self.endpoints[device] for device in devices}))
        resources = endpoints if kind in self.independent else (*devices, *endpoints)
        metadata.update(communication_type=kind, group=group, endpoints=endpoints,
                        topology=self.topology, occupies_gpu=kind not in self.independent)
        return Placement(devices, group), resources

    def ep_group(self, devices):
        for name, data in self.ep_groups.items():
            if set(devices).issubset(data["members"]):
                return name, data
        raise ValueError("expanded AICB requires an explicit EP group for this Stage")


class ExpandedStageBuilder:
    def __init__(self, graph_id, execution_time, placement, backend, is_last_stage, *,
                 payload_bytes=None, tp_calibration=None):
        self.graph_id = graph_id
        self.time = execution_time
        self.placement = placement
        self.backend = backend
        self.is_last_stage = is_last_stage
        self.payload_bytes = payload_bytes
        self.tp_calibration = tp_calibration

    def build(self, context):
        tasks = []
        devices = self.placement.devices[context.replica_id, context.stage_id]
        source = f"{self.backend}.ExecutionTime"

        def add(op, kind, components, unit="ms", *, layer=None, comm=None, evidence=None):
            for value in components.values():
                finite_nonnegative(value)
            raw = fsum(components.values())
            factor = {"ms": 1e-3, "ns": 1e-9, "s": 1.0}[unit]
            metadata = dict(op=op, layer=layer, components=components, source=source)
            if comm:
                comm_kind, group, members, details = comm
                component = comm_kind
                metadata.update(details)
                if comm_kind == "tp" and self.tp_calibration:
                    scale = self.tp_calibration.get("scale", 1)
                    offset = self.tp_calibration.get("offset_s", 0)
                    metadata.update(uncalibrated_raw_value=raw, tp_cost_scale=scale, tp_cost_offset_s=offset)
                    raw = raw * scale + offset / factor
                    evidence = self.tp_calibration["evidence"]
                placement, resources = self.placement.communication(comm_kind, group, members, metadata)
            elif op.startswith("cpu."):
                component = "cpu"
                placement, resources = Placement(), (f"cpu:{context.replica_id}",)
            elif kind == "sync":
                component = "sync"
                placement, resources = Placement(), ()
            else:
                component = "compute"
                placement, resources = Placement(devices), devices
            task_id = f"layer{layer}.{op}" if layer is not None else op
            cost = CostEstimate(raw * factor, source, raw, unit, factor,
                                evidence or "vidur/entities/execution_time.py:ExecutionTime",
                                (component,))
            if cost.duration_s == 0:
                resources = ()
            tasks.append(TaskSpec(task_id, kind, placement,
                                  tuple(ResourceDemand(resource, 1, "permits") for resource in resources),
                                  cost, metadata))

        def properties(fields):
            return {field: getattr(self.time, field) for field in fields}

        add("cpu.prepare", "compute", properties(CPU_PRE))
        if self.backend == "aicb":
            group, ep = self.placement.ep_group(devices)
            layers, phase, ep_size = self.time.expanded_aicb_profile()
            if len(ep["members"]) != ep_size:
                raise ValueError(f"EP membership count differs from AICB profile EP={ep_size}")
            if phase not in ("prefill", "decode"):
                raise ValueError(f"unsupported AICB profile phase: {phase}")
            for layer in range(self.time.num_layers):
                profile = layers.get(layer, {})
                for op in ("attention", "mlp", "moe"):
                    if "comp_time" not in profile.get(op, {}):
                        raise ValueError(f"missing AICB compute profile for layer {layer} {op}")
                    add(f"{op}.compute", "compute", {op: profile[op]["comp_time"]}, "ns", layer=layer)
                wire_bytes = finite_nonnegative(profile["moe"].get("comm_size"))
                if not float(wire_bytes).is_integer():
                    raise ValueError("AICB EP payload must be integer bytes")
                bandwidth = ep["bandwidth_bytes_per_s"][phase]
                add("moe.ep", "comm", {"ep_aggregate": wire_bytes / bandwidth}, "s", layer=layer,
                    comm=("ep", group, tuple(ep["members"]), {
                        "payload_bytes": int(wire_bytes), "bandwidth_bytes_per_s": bandwidth,
                        "granularity": "aggregate", "phase": phase,
                    }), evidence=ep["evidence"])
        else:
            for local_layer in range(self.time.num_layers):
                layer = context.stage_id * self.time.num_layers + local_layer
                for op, fields, cost_field in (
                    ("attention", ATTENTION, "attention_all_reduce_time"),
                    ("mlp", MLP, "mlp_all_reduce_time"),
                ):
                    add(f"{op}.compute", "compute", properties(fields), layer=layer)
                    if self.placement.tp > 1:
                        add(f"{op}.tp", "comm", properties((cost_field,)), layer=layer,
                            comm=("tp", f"tp:{context.replica_id}:{context.stage_id}", devices,
                                  {"collective": "all_reduce", "payload_bytes": self.payload_bytes}))
                add("residual_add", "compute", properties(("add_time",)), layer=layer)
        if not self.is_last_stage:
            next_devices = self.placement.devices[context.replica_id, context.stage_id + 1]
            add("pipeline.send_recv", "comm", properties(("pipeline_parallel_communication_time",)),
                comm=("pp", f"pp:{context.replica_id}:{context.stage_id}", (*devices, *next_devices),
                      {"rank_pairs": list(zip(devices, next_devices)), "payload_bytes": self.payload_bytes}))
        add("cpu.finish", "compute", properties(CPU_POST))
        add("terminal", "sync", {}, "s", evidence="zero-duration terminal")
        return GraphFragment("1.0", self.graph_id, context, tuple(tasks),
                             tuple((a.task_id, b.task_id) for a, b in zip(tasks, tasks[1:])), "terminal")


class ExpandedDagAdapter(CoarseDagAdapter):
    def __init__(self, stage_keys, tp, backend, model, settings):
        stage_keys = tuple(stage_keys)
        self.backend = backend
        self.placement = StagePlacement(stage_keys, tp, settings)
        self.tp_calibration = settings.get("tp_cost_calibration")
        if self.tp_calibration is not None:
            calibration = self.tp_calibration
            pp = max(stage for _, stage in stage_keys) + 1
            if (backend != "simai_analytical" or
                    (calibration.get("model"), calibration.get("tp"), calibration.get("pp")) != (model, tp, pp)
                    or not calibration.get("evidence")
                    or finite_nonnegative(calibration.get("scale", 1)) == 0):
                raise ValueError("TP calibration requires a positive scale and matching analytical model/TP/PP scope")
            finite_nonnegative(calibration.get("offset_s", 0))
        if backend == "aicb":
            if model not in AICB_MODELS or tp != 1 or any(stage != 0 for _, stage in stage_keys):
                raise ValueError("expanded AICB requires a supported special model, PP=1 and TP=1 (TP cost unavailable)")
            for devices in self.placement.devices.values():
                self.placement.ep_group(devices)
        elif backend not in DENSE_BACKENDS:
            raise ValueError(f"unsupported expanded backend: {backend}")
        elif model in AICB_MODELS:
            raise ValueError("expanded MoE requires AICB layer and EP cost evidence")
        super().__init__(stage_keys, resources=self.placement.resources)

    def submit_stage(self, now, replica_id, stage_id, is_last_stage, batch, batch_stage,
                     *, on_stage_start=None, execution_time=None, record=None):
        graph_id, context = self._identity(replica_id, stage_id, batch)
        payload = None
        if self.backend != "aicb" and (self.placement.tp > 1 or not is_last_stage):
            payload = execution_time.collective_payload_bytes(batch._total_num_tokens_rounded)
        fragment = ExpandedStageBuilder(graph_id, execution_time, self.placement,
                                        self.backend, is_last_stage, payload_bytes=payload,
                                        tp_calibration=self.tp_calibration).build(context)
        service = fsum(task.cost.duration_s for task in fragment.tasks)
        uncalibrated_service = fsum(
            task.metadata.get("uncalibrated_raw_value", task.cost.raw_value) * task.cost.conversion_to_s
            for task in fragment.tasks
        )
        if self.backend != "aicb" and not isclose(
                uncalibrated_service, batch_stage.execution_time, rel_tol=1e-12, abs_tol=1e-15):
            raise ValueError(f"expanded Stage cost mismatch: {uncalibrated_service} vs {batch_stage.execution_time}")
        if record is not None:
            record.update(graph_id=graph_id, expanded_service_s=service,
                          actual_service_interval_s=None, graph_resource_wait_s=None)

        def finish(time):
            graph = self.executor.graph_snapshot(graph_id)
            elapsed = time - batch_stage.scheduled_at
            model_service = fsum(task.cost.duration_s for task in graph.fragment.tasks
                                 if not task.task_id.startswith("cpu."))
            batch_stage.settle_expanded_execution(time, model_service)
            if record is not None:
                final_service = fsum(task.cost.duration_s for task in graph.fragment.tasks)
                internal_wait = fsum(task.resource_wait_s for task in graph.tasks.values()
                                     if task.spec.task_id != fragment.tasks[0].task_id)
                record.update(expanded_service_s=final_service, actual_service_interval_s=elapsed,
                              graph_resource_wait_s=internal_wait)

        return self._submit(fragment, now, replica_id, stage_id, is_last_stage, batch, batch_stage,
                            on_stage_start, finish)
