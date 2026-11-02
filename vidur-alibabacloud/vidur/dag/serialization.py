"""JSON/dataclass conversion with validated, isolated submission snapshots."""
from dataclasses import asdict
import json

from schemas.dag.v1.contracts import (
    CostEstimate, GraphContext, GraphFragment, Placement, ResourceDemand, TaskSpec,
)
from schemas.dag.v1.io import read_json
from schemas.dag.v1.validation import validate_graph


def graph_to_dict(fragment: GraphFragment) -> dict:
    if not isinstance(fragment, GraphFragment):
        raise ValueError("expected GraphFragment")
    try:
        # JSON normalizes tuples and copies metadata; it also rejects NaN/Infinity.
        return json.loads(json.dumps(asdict(fragment), allow_nan=False))
    except (TypeError, OverflowError, RecursionError) as exc:
        raise ValueError(f"graph is not JSON serializable: {exc}") from exc


def task_from_dict(data: dict) -> TaskSpec:
    return TaskSpec(
        task_id=data["task_id"], kind=data["kind"],
        placement=Placement(tuple(data["placement"]["device_ids"]),
                            data["placement"]["comm_group"]),
        demands=tuple(ResourceDemand(**d) for d in data["demands"]),
        cost=CostEstimate(**dict(data["cost"], includes=tuple(data["cost"]["includes"]),
                                 unknown_components=tuple(data["cost"]["unknown_components"]))),
        metadata=data.get("metadata", {}),
    )


def graph_from_dict(data: dict) -> GraphFragment:
    try:
        data = json.loads(json.dumps(data, allow_nan=False))
    except (TypeError, OverflowError, RecursionError) as exc:
        raise ValueError(f"graph is not JSON serializable: {exc}") from exc
    validate_graph(data)
    context = dict(data["context"], request_ids=tuple(data["context"]["request_ids"]))
    return GraphFragment(
        schema_version=data["schema_version"], graph_id=data["graph_id"],
        context=GraphContext(**context), tasks=tuple(task_from_dict(t) for t in data["tasks"]),
        edges=tuple(tuple(e) for e in data["edges"]), terminal_task_id=data["terminal_task_id"],
    )


def load_graph(path) -> GraphFragment:
    return graph_from_dict(read_json(path))


def snapshot_graph(fragment: GraphFragment) -> GraphFragment:
    return graph_from_dict(graph_to_dict(fragment))
