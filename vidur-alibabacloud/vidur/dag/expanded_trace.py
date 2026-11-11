"""Audit the submitted cost snapshot and observed compute/communication overlap."""
import json

from vidur.dag.serialization import graph_to_dict
from vidur.dag.trace import write_csv, write_json


def overlap_rows(intervals):
    active = {"compute": {}, "comm": {}}
    events = []
    for kind, owner, start, end in intervals:
        if end > start:
            events.extend(((start, True, kind, owner, end), (end, False, kind, owner, end)))
    for time, starting, kind, owner, end in sorted(events):
        if not starting:
            del active[kind][owner]
            continue
        other = "comm" if kind == "compute" else "compute"
        for other_owner, other_end in active[other].items():
            compute, comm = (owner, other_owner) if kind == "compute" else (other_owner, owner)
            overlap_end = min(end, other_end)
            yield (*compute, *comm, time, overlap_end, overlap_end - time)
        active[kind][owner] = end


def write_expanded_results(output, executor):
    graph_dir = output / "graphs"
    graph_dir.mkdir(exist_ok=True)
    costs, intervals = [], []
    for gid, graph in executor.graphs.items():
        context = graph.fragment.context
        write_json(graph_dir / f"stage-{context.iteration_id:06d}.graph.json", graph_to_dict(graph.fragment))
        for task in graph.tasks.values():
            spec = task.spec
            cost = spec.cost
            costs.append(dict(graph_id=gid, task_id=spec.task_id, kind=spec.kind,
                              layer=spec.metadata.get("layer"), op=spec.metadata.get("op"),
                              raw_value=cost.raw_value, raw_unit=cost.raw_unit, duration_s=cost.duration_s,
                              conversion_to_s=cost.conversion_to_s, source=cost.source, evidence=cost.evidence,
                              includes=json.dumps(cost.includes), metadata=json.dumps(spec.metadata)))
            end = task.end_at if task.end_at is not None else task.resource_released_at
            if spec.kind in ("compute", "comm") and task.start_at is not None and end is not None:
                intervals.append((spec.kind, (gid, spec.task_id), task.start_at, end))
    write_csv(output / "cost-breakdown.csv", (
        "graph_id", "task_id", "kind", "layer", "op", "raw_value", "raw_unit", "duration_s",
        "conversion_to_s", "source", "evidence", "includes", "metadata",
    ), costs)
    fields = ("compute_graph_id", "compute_task_id", "comm_graph_id", "comm_task_id",
              "start_at_s", "end_at_s", "overlap_s")
    write_csv(output / "overlap.csv", fields, (dict(zip(fields, row)) for row in overlap_rows(intervals)))
