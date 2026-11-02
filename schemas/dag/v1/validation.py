"""Shared DAG v1 validation; no simulator or execution imports."""
import math

from pathlib import Path

from .io import finite_nonnegative, read_json
from jsonschema import Draft202012Validator, ValidationError

SCHEMA_PATH = Path(__file__).with_name("graph.schema.json")
SCHEMA = read_json(SCHEMA_PATH)
Draft202012Validator.check_schema(SCHEMA)
VALIDATOR = Draft202012Validator(SCHEMA)
SCALES = {"s": 1.0, "ms": 1e-3, "us": 1e-6, "ns": 1e-9}


def check_finite_tree(value):
    """Reject non-finite floats even inside opaque metadata."""
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non-finite graph value")
    if isinstance(value, dict):
        for item in value.values():
            check_finite_tree(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            check_finite_tree(item)


def validate_graph(graph):
    check_finite_tree(graph)
    try:
        VALIDATOR.validate(graph)
    except ValidationError as exc:
        raise ValueError(f"invalid graph: {exc.message}") from exc
    tasks = {t["task_id"]: t for t in graph["tasks"]}
    if len(tasks) != len(graph["tasks"]):
        raise ValueError("duplicate task ID")
    terminal = graph["terminal_task_id"]
    if terminal not in tasks:
        raise ValueError("missing terminal")
    children = {tid: [] for tid in tasks}
    indegrees = dict.fromkeys(tasks, 0)
    for source, target in graph["edges"]:
        if source not in tasks or target not in tasks:
            raise ValueError("edge references missing task")
        children[source].append(target)
        indegrees[target] += 1
    ready = [tid for tid, degree in indegrees.items() if degree == 0]
    visited = []
    for tid in ready:
        visited.append(tid)
        for child in children[tid]:
            indegrees[child] -= 1
            if indegrees[child] == 0:
                ready.append(child)
    if len(visited) != len(tasks):
        raise ValueError("cycle")
    if [tid for tid in tasks if not children[tid]] != [terminal]:
        raise ValueError("every leaf must converge on the sole terminal")
    end = tasks[terminal]
    if end["kind"] != "sync" or end["cost"]["duration_s"] != 0 or end["demands"]:
        raise ValueError("terminal must be zero-duration resource-free sync")
    for task in tasks.values():
        cost = task["cost"]
        duration = finite_nonnegative(cost["duration_s"])
        raw = finite_nonnegative(cost["raw_value"])
        scale = finite_nonnegative(cost["conversion_to_s"])
        if scale != SCALES[cost["raw_unit"]]:
            raise ValueError("incorrect unit conversion factor")
        if not math.isclose(duration, raw * scale, rel_tol=1e-12, abs_tol=1e-15):
            raise ValueError("duration disagrees with raw value/unit")
        ids = [d["resource_id"] for d in task["demands"]]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate resource demand")
    if any(t["kind"] == "coarse" for t in tasks.values()) and any(
            t["kind"] in ("compute", "comm") for t in tasks.values()):
        raise ValueError("coarse and expanded charged tasks cannot coexist in a fragment")
    return visited


def validate_expectation(graph, expectation):
    """Check supplied schedules algebraically, without generating a schedule."""
    validate_graph(graph)
    tasks = {t["task_id"]: t for t in graph["tasks"]}
    for scenario in expectation["scenarios"]:
        schedule = scenario["schedule_s"]
        if set(schedule) != set(tasks):
            raise ValueError("expected schedule must cover all tasks")
        overrides = scenario.get("demands_override", {})
        if set(overrides) - set(tasks):
            raise ValueError("override references unknown task")
        intervals = {}
        for tid, task in tasks.items():
            start, finish = map(finite_nonnegative, schedule[tid])
            if not math.isclose(finish - start, task["cost"]["duration_s"], abs_tol=1e-15):
                raise ValueError("expected task duration mismatch")
            demands = overrides.get(tid, task["demands"])
            for demand in demands:
                capacity = scenario["capacities"][demand["resource_id"]]
                if demand["unit"] != capacity["unit"] or demand["amount"] > capacity["amount"]:
                    raise ValueError("resource unit/capacity mismatch")
                if finish > start:  # Empty intervals do not occupy time.
                    intervals.setdefault(demand["resource_id"], []).extend([
                        (start, demand["amount"]), (finish, -demand["amount"])])
        for source, target in graph["edges"]:
            if schedule[source][1] > schedule[target][0] + 1e-15:
                raise ValueError("expected dependency violated")
        for resource, events in intervals.items():
            used = 0
            for _, change in sorted(events):  # releases before acquires at equal time
                used += change
                if used < 0 or used > scenario["capacities"][resource]["amount"]:
                    raise ValueError("expected resource overcommit")
        if not math.isclose(max(t[1] for t in schedule.values()), scenario["makespan_s"], abs_tol=1e-15):
            raise ValueError("expected makespan mismatch")
