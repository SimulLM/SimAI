"""Inspectable execution results, without deriving schedules from expectations."""
import csv
import json
from pathlib import Path

from schemas.dag.v1.contracts import TaskState

TIMELINE_FIELDS = (
    "graph_id", "task_id", "kind", "submission_sequence", "state", "ready_at_s",
    "start_at_s", "end_at_s", "scheduled_finish_at_s", "duration_s", "resource_wait_s",
    "remaining_predecessors", "completion_count", "resource_mode", "demands", "placement",
    "cost_source", "raw_value", "raw_unit", "conversion_to_s", "cost_evidence", "failure",
    "resource_released_at_s",
)
EVENT_FIELDS = ("time_s", "insertion_sequence", "kind", "graph_id", "task_id")
RESOURCE_TIMELINE_FIELDS = (
    "resource_id", "unit", "amount", "graph_id", "task_id", "start_at_s", "end_at_s",
)


def write_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                          encoding="utf-8")


def write_csv(path, fields, rows):
    with Path(path).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def snapshot(runner, *, error=None):
    rows, graphs = [], []
    for gid, graph in runner.executor.graphs.items():
        observed_until = graph.finished_at if graph.finished_at is not None else runner.now
        unfinished = []
        for tid, task in graph.tasks.items():
            spec = task.spec
            wait = task.resource_wait_s
            if task.resource_wait_started_at is not None:
                wait += observed_until - task.resource_wait_started_at
            rows.append(dict(
                graph_id=gid, task_id=tid, kind=spec.kind, submission_sequence=task.sequence,
                state=task.state.value, ready_at_s=task.ready_at, start_at_s=task.start_at,
                end_at_s=task.end_at, scheduled_finish_at_s=task.scheduled_finish_at,
                duration_s=spec.cost.duration_s, resource_wait_s=wait,
                remaining_predecessors=task.remaining_predecessors, completion_count=task.completion_count,
                resource_mode=runner.executor.resource_mode,
                demands=json.dumps([dict(resource_id=d.resource_id, amount=d.amount, unit=d.unit)
                                    for d in spec.demands], ensure_ascii=False, sort_keys=True),
                placement=json.dumps(dict(device_ids=spec.placement.device_ids,
                                          comm_group=spec.placement.comm_group), ensure_ascii=False, sort_keys=True),
                cost_source=spec.cost.source, raw_value=spec.cost.raw_value, raw_unit=spec.cost.raw_unit,
                conversion_to_s=spec.cost.conversion_to_s, cost_evidence=spec.cost.evidence,
                failure=task.failure,
                resource_released_at_s=task.resource_released_at,
            ))
            if task.state not in (TaskState.COMPLETED, TaskState.FAILED):
                unfinished.append(dict(task_id=tid, state=task.state.value,
                    unfinished_predecessors=[source for source, target in graph.fragment.edges
                                             if target == tid and graph.tasks[source].state != TaskState.COMPLETED],
                    resource_wait=task.resource_wait_started_at is not None))
        graphs.append(dict(
            graph_id=gid, state=graph.state, submitted_at_s=graph.submitted_at,
            finished_at_s=graph.finished_at,
            makespan_s=(graph.finished_at - graph.submitted_at if graph.state == "COMPLETED" else None),
            task_count=len(graph.tasks), completed_count=graph.completed_count,
            terminal_callback_count=graph.callback_count, failure=graph.failure,
            cleanup_errors=graph.cleanup_errors,
            unreleased_leases=[dict(task_id=tid, lease_id=t.lease.lease_id,
                                   release_attempted=t.release_attempted)
                               for tid, t in graph.tasks.items() if t.lease is not None],
            unfinished_tasks=unfinished,
        ))
    rows.sort(key=lambda row: row["submission_sequence"])
    error = error or runner.failure
    success = error is None and bool(graphs) and all(g["state"] == "COMPLETED" for g in graphs)
    summary = dict(
        status="passed" if success else "failed", error=error,
        final_time_s=runner.now, resource_mode=runner.executor.resource_mode,
        resource_capacity_validated=False, hardware_accuracy_claim=False,
        event_count=len(runner.events), event_queue_peak=runner.queue_peak,
        pending_event_count=runner.pending_event_count,
        task_count=len(rows), graphs=graphs,
    )
    return rows, summary


def write_results(output, runner, *, error=None):
    output = Path(output)
    rows, summary = snapshot(runner, error=error)
    write_csv(output / "timeline.csv", TIMELINE_FIELDS, rows)
    write_csv(output / "events.csv", EVENT_FIELDS, runner.events)
    # Import lazily: the default phase-2 path remains independent of capacity code.
    from .resources import CapacityResourceManager, resource_timeline
    manager = getattr(runner.executor, "_resources", None)
    intervals = resource_timeline(runner.executor)
    write_csv(output / "resource_timeline.csv", RESOURCE_TIMELINE_FIELDS, [
        dict(resource_id=item.resource_id, unit=item.unit, amount=item.amount,
             graph_id=item.owner[0], task_id=item.owner[1], start_at_s=item.start_s,
             end_at_s=item.end_s)
        for item in intervals
    ])
    if isinstance(manager, CapacityResourceManager):
        summary["resource_capacity"] = manager.usage_snapshot()
        # A manager type alone is not validation. Check the observed half-open
        # intervals independently, as well as confirmed cleanup of task leases.
        errors = []
        for resource_id, resource in summary["resource_capacity"].items():
            if not 0 <= resource["used"] <= resource["capacity"]:
                errors.append(f"invalid final usage: {resource_id}")
            events = []
            for item in intervals:
                if item.resource_id != resource_id:
                    continue
                if item.unit != resource["unit"] or item.end_s < item.start_s:
                    errors.append(f"invalid interval: {item.owner}")
                if item.start_s < item.end_s:
                    events.extend(((item.start_s, item.amount), (item.end_s, -item.amount)))
            used = 0
            for _, change in sorted(events):  # releases precede acquires at the same time
                used += change
                if not 0 <= used <= resource["capacity"]:
                    errors.append(f"interval capacity violation: {resource_id}")
        for graph in runner.executor.graphs.values():
            if graph.cleanup_errors:
                errors.extend(graph.cleanup_errors)
            for task in graph.tasks.values():
                if task.lease is not None:
                    errors.append(f"unreleased lease: {task.spec.task_id}")
                if task.start_at is not None and task.spec.demands and task.resource_released_at is None:
                    errors.append(f"unconfirmed resource interval: {task.spec.task_id}")
        summary["resource_capacity_check_errors"] = errors
        summary["resource_capacity_validated"] = summary["status"] == "passed" and not errors
    write_json(output / "summary.json", summary)
    return summary
