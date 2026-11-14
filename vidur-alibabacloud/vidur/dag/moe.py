"""Per-iteration MoE routing and explicit, provenance-bearing cost providers.

Routing matrices count assignments, including local assignments. Network tasks
only charge off-device cells. No profile is inferred from a destination count.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
from numbers import Integral
from pathlib import Path

from schemas.dag.v1.contracts import CostEstimate
from schemas.dag.v1.io import finite_nonnegative, read_json


def integer(value, name, *, minimum=0):
    if isinstance(value, bool) or not isinstance(value, Integral) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return int(value)


def fields(data, allowed, name):
    if not isinstance(data, dict) or set(data) - set(allowed):
        raise ValueError(f"invalid {name} fields")


@dataclass(frozen=True)
class Assignment:
    source: str
    token: int
    expert: str


@dataclass(frozen=True)
class RoutingResult:
    iteration: int
    layer: int
    phase: str
    top_k: int
    tokens_by_source: tuple[tuple[str, int], ...]
    assignments: tuple[Assignment, ...]
    strategy: str

    def validate(self, experts):
        integer(self.iteration, "iteration")
        integer(self.layer, "layer")
        integer(self.top_k, "top_k", minimum=1)
        if self.phase not in ("prefill", "decode") or self.top_k > len(experts):
            raise ValueError("invalid phase or top_k exceeds expert count")
        tokens = dict(self.tokens_by_source)
        if len(tokens) != len(self.tokens_by_source) or not tokens:
            raise ValueError("token sources must be unique and nonempty")
        devices = set(experts.values())
        for source, count in tokens.items():
            if source not in devices:
                raise ValueError(f"unknown source device: {source}")
            integer(count, "token count")
        seen, counts = set(), Counter()
        for a in self.assignments:
            integer(a.token, "token index")
            if (not isinstance(a.source, str) or not isinstance(a.expert, str) or
                    a.source not in tokens or a.token >= tokens[a.source] or a.expert not in experts):
                raise ValueError("assignment references unknown source, token or expert")
            identity = (a.source, a.token, a.expert)
            if identity in seen:
                raise ValueError("duplicate token/expert assignment")
            seen.add(identity)
            counts[a.source, a.token] += 1
        if len(self.assignments) != sum(tokens.values()) * self.top_k or any(
                counts[source, token] != self.top_k
                for source, count in tokens.items() for token in range(count)):
            raise ValueError("routing must conserve tokens * top_k without dropping assignments")
        return self

    @property
    def digest(self):
        return sha256(json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    @property
    def expert_counts(self):
        return Counter(a.expert for a in self.assignments)

    def matrix(self, experts):
        devices = sorted(set(experts.values()))
        result = {source: dict.fromkeys(devices, 0) for source in devices}
        for a in self.assignments:
            result[a.source][experts[a.expert]] += 1
        return result

    def to_dict(self):
        return dict(iteration=self.iteration, layer=self.layer, phase=self.phase,
                    top_k=self.top_k, tokens_by_source=dict(self.tokens_by_source), strategy=self.strategy,
                    assignments=[dict(source=a.source, token=a.token, expert=a.expert) for a in self.assignments])


def route(tokens_by_source, experts, *, top_k, iteration, layer, phase,
          strategy="balanced", seed=0, trace=None):
    """Deterministic routing; a trace supplies complete source/token/expert IDs."""
    top_k = integer(top_k, "top_k", minimum=1)
    iteration = integer(iteration, "iteration")
    layer = integer(layer, "layer")
    seed = integer(seed, "seed")
    if not experts or top_k > len(experts):
        raise ValueError("top_k exceeds expert count")
    tokens_by_source = {source: integer(count, "token count") for source, count in tokens_by_source.items()}
    assignments = []
    names = tuple(sorted(experts))
    if strategy == "trace":
        if not isinstance(trace, list):
            raise ValueError("trace routing requires an assignment list")
        for entry in trace:
            fields(entry, ("source", "token", "experts"), "trace assignment")
            if not isinstance(entry.get("experts"), list):
                raise ValueError("trace assignment requires an expert list")
            assignments.extend(Assignment(entry.get("source"), entry.get("token"), expert)
                               for expert in entry["experts"])
    elif strategy in ("balanced", "hotspot"):
        index = 0
        for source, count in sorted(tokens_by_source.items()):
            for token in range(count):
                start = (index * top_k + iteration + layer + seed) % len(names) if strategy == "balanced" else seed % len(names)
                assignments.extend(Assignment(source, token, names[(start + k) % len(names)])
                                   for k in range(top_k))
                index += 1
    else:
        raise ValueError(f"unknown routing strategy: {strategy}")
    return RoutingResult(iteration, layer, phase, top_k, tuple(sorted(tokens_by_source.items())),
                         tuple(assignments), strategy).validate(experts)


class MoeConfig:
    """The phase-7 input contract; independent of the frozen DAG v1 schema."""

    def __init__(self, data, *, base_dir=None):
        fields(data, ("schema_version", "group", "experts", "routing", "cost", "scope"), "MoE config")
        if data.get("schema_version") != "1.0" or not isinstance(data.get("group"), str) or not data["group"]:
            raise ValueError("MoE requires schema_version=1.0 and a named EP group")
        self.group = data["group"]
        self.experts = data.get("experts")
        if (not isinstance(self.experts, dict) or not self.experts or
                any(not isinstance(k, str) or not k or not isinstance(v, str) or not v
                    for k, v in self.experts.items())):
            raise ValueError("experts must map nonempty expert IDs to device IDs")
        self.experts = dict(self.experts)
        self.routing = deepcopy(data.get("routing", {}))
        fields(self.routing, ("top_k", "patterns", "seed", "traces"), "routing")
        self.top_k = integer(self.routing.get("top_k"), "top_k", minimum=1)
        self.seed = integer(self.routing.get("seed", 0), "seed")
        self.patterns = self.routing.get("patterns", ["balanced"])
        if (self.top_k > len(self.experts) or not isinstance(self.patterns, list) or not self.patterns
                or any(p not in ("balanced", "hotspot", "trace") for p in self.patterns)):
            raise ValueError("invalid MoE routing patterns or top_k")
        self.traces = self.routing.get("traces", [])
        if not isinstance(self.traces, list) or ("trace" in self.patterns and not self.traces):
            raise ValueError("trace routing requires per-iteration traces")
        self.scope = deepcopy(data.get("scope", {}))
        if not isinstance(self.scope, dict):
            raise ValueError("MoE scope must be an object")
        self.cost = MoeCosts(data.get("cost"), self.scope, base_dir=base_dir)

    def routing_result(self, tokens, *, iteration, layer, phase):
        pattern = self.patterns[iteration % len(self.patterns)]
        trace = None
        if pattern == "trace":
            # Never silently recycle another round's routing trace.
            if iteration >= len(self.traces):
                raise ValueError(f"missing routing trace for iteration {iteration}")
            trace = self.traces[iteration]
        return route(tokens, self.experts, top_k=self.top_k, iteration=iteration, layer=layer,
                     phase=phase, strategy=pattern, seed=self.seed, trace=trace)


class MoeCosts:
    """Synthetic logic costs or exact expert-load lookup, never silent fallback."""

    def __init__(self, data, scope, *, base_dir=None):
        fields(data, ("mode", "evidence", "route_s", "up_s_per_assignment", "down_s_per_assignment",
                      "dispatch_bytes_per_assignment", "combine_bytes_per_assignment",
                      "latency_s", "profiles"), "MoE cost")
        self.mode = data.get("mode")
        self.evidence = data.get("evidence")
        if self.mode not in ("synthetic", "profile") or not isinstance(self.evidence, str) or not self.evidence.strip():
            raise ValueError("MoE costs require synthetic/profile mode and evidence")
        self.route_s = finite_nonnegative(data.get("route_s", 0))
        self.latency_s = finite_nonnegative(data.get("latency_s", 0))
        self.dispatch_bytes = integer(data.get("dispatch_bytes_per_assignment"), "dispatch bytes", minimum=1)
        self.combine_bytes = integer(data.get("combine_bytes_per_assignment"), "combine bytes", minimum=1)
        self.profiles = {}
        if self.mode == "synthetic":
            if data.get("profiles"):
                raise ValueError("synthetic costs cannot contain measured profile records")
            self.up = finite_nonnegative(data.get("up_s_per_assignment"))
            self.down = finite_nonnegative(data.get("down_s_per_assignment"))
        else:
            if any(k in data for k in ("up_s_per_assignment", "down_s_per_assignment")):
                raise ValueError("profile costs cannot fall back to a synthetic slope")
            required = {"model", "device", "tp", "pp", "ep", "dtype"}
            if (not required.issubset(scope) or any(scope[k] in (None, "", "unknown") for k in required)
                    or any(not isinstance(scope[k], str) or not scope[k].strip()
                           for k in ("model", "device", "dtype"))
                    or any(type(scope[k]) is not int or scope[k] < 1 for k in ("tp", "pp", "ep"))):
                raise ValueError("profile costs require complete model/device/TP/PP/EP/dtype scope")
            records = data.get("profiles")
            if not isinstance(records, list) or not records:
                raise ValueError("profile costs require exact expert-load records")
            for record in records:
                fields(record, ("expert", "phase", "assignments", "up_s", "down_s", "scope",
                                "nature", "evidence"), "expert profile")
                count = integer(record.get("assignments"), "profile assignments", minimum=1)
                if (record.get("scope") != scope or record.get("phase") not in ("prefill", "decode")
                        or not isinstance(record.get("expert"), str) or not record["expert"]
                        or record.get("nature") not in ("measured", "simulated", "estimated")):
                    raise ValueError("expert profile scope, identity or nature mismatch")
                evidence = record.get("evidence")
                if not isinstance(evidence, list) or not evidence:
                    raise ValueError("expert profile requires hashed evidence")
                for item in evidence:
                    fields(item, ("path", "sha256"), "profile evidence")
                    path = Path(item.get("path", ""))
                    if not path.is_absolute():
                        path = Path(base_dir or ".") / path
                    if not path.is_file() or sha256(path.read_bytes()).hexdigest() != item.get("sha256"):
                        raise ValueError("expert profile evidence is missing or has a different hash")
                key = (record["expert"], record["phase"], count)
                if key in self.profiles:
                    raise ValueError("duplicate expert-load profile")
                self.profiles[key] = (finite_nonnegative(record.get("up_s")),
                                      finite_nonnegative(record.get("down_s")), record["nature"],
                                      json.dumps(evidence, sort_keys=True))

    def estimate(self, value, source, includes, evidence=None):
        value = finite_nonnegative(value)
        return CostEstimate(value, source, value, "s", 1.0, evidence or self.evidence, (includes,))

    def routing(self):
        return self.estimate(self.route_s, "synthetic_moe_route" if self.mode == "synthetic"
                             else "estimated_moe_route", "compute")

    def expert(self, expert, phase, count, operation):
        integer(count, "expert assignments", minimum=1)
        if operation not in ("up", "down"):
            raise ValueError("expert operation must be up or down")
        if self.mode == "synthetic":
            return self.estimate(count * (self.up if operation == "up" else self.down),
                                 "synthetic_moe_expert", "compute")
        key = (expert, phase, count)
        if key not in self.profiles:
            raise ValueError(f"no exact expert profile for {key}")
        up, down, nature, evidence = self.profiles[key]
        return self.estimate(up if operation == "up" else down, f"expert_profile:{nature}", "compute", evidence)

    def transfer(self, payload, bandwidth):
        integer(payload, "wire bytes", minimum=1)
        bandwidth = finite_nonnegative(bandwidth)
        if not bandwidth:
            raise ValueError("EP bandwidth must be positive")
        return self.estimate(self.latency_s + payload / bandwidth,
                             "synthetic_moe_transfer" if self.mode == "synthetic" else "estimated_moe_transfer", "ep")


def load_config(path):
    path = Path(path)
    return MoeConfig(read_json(path), base_dir=path.resolve().parent)
