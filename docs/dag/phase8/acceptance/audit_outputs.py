"""Recompute timing, graph and resource invariants from saved CLI artifacts."""
import argparse
import csv
import json
import math
from pathlib import Path

TOLERANCE = 1e-12


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def audit(folder):
    errors = []
    def check(condition, message):
        if not condition:
            errors.append(message)
    timeline = rows(folder / "timeline.csv")
    tasks = {(r["graph_id"], r["task_id"]): r for r in timeline}
    summary = read(folder / "summary.json")
    check(len(tasks) == len(timeline), "duplicate task rows")
    check(summary["pending_event_count"] == 0, "pending DAG events")
    check(all(g["terminal_callback_count"] == 1 for g in summary["graphs"]), "terminal count")
    for key, row in tasks.items():
        ready, start, end, duration, wait = (float(row[k]) for k in
            ("ready_at_s", "start_at_s", "end_at_s", "duration_s", "resource_wait_s"))
        check(all(math.isfinite(v) and v >= 0 for v in (ready, start, end, duration, wait)), str(key) + " invalid time")
        check(row["state"] == "COMPLETED" and int(row["completion_count"]) == 1, str(key) + " completion")
        check(ready <= start + TOLERANCE and start <= end + TOLERANCE, str(key) + " time order")
        check(abs(end-start-duration) <= TOLERANCE, str(key) + " duration")
        check(abs(start-ready-wait) <= TOLERANCE, str(key) + " waiting")
    graphs = {}
    for path in (folder / "graphs").glob("*.graph.json"):
        graph = read(path)
        gid = graph["graph_id"]
        graphs[gid] = graph
        check(len(graph["tasks"]) == sum(k[0] == gid for k in tasks), gid + " task count")
        for task in graph["tasks"]:
            key = gid, task["task_id"]
            check(key in tasks, str(key) + " missing timeline")
            if key in tasks:
                check(abs(float(tasks[key]["duration_s"]) - task["cost"]["duration_s"]) <= TOLERANCE, str(key) + " cost mismatch")
        for a, b in graph["edges"]:
            check(float(tasks[gid, a]["end_at_s"]) <= float(tasks[gid, b]["start_at_s"]) + TOLERANCE, gid + " dependency")
    intervals = rows(folder / "resource_timeline.csv")
    capacities = summary["resource_capacity"]
    for resource, capacity in capacities.items():
        check(capacity["used"] == 0, resource + " leaked final resource")
        changes = []
        for row in intervals:
            if row["resource_id"] != resource:
                continue
            start, end, amount = float(row["start_at_s"]), float(row["end_at_s"]), int(row["amount"])
            check(row["unit"] == capacity["unit"] and start <= end and amount > 0, resource + " invalid interval")
            if end > start:
                changes.extend(((start, amount), (end, -amount)))
        used = 0
        for _, change in sorted(changes):
            used += change
            check(0 <= used <= capacity["capacity"], resource + " exceeded capacity")
        check(used == 0, resource + " unclosed interval")
    check(all(r["resource_id"] in capacities for r in intervals), "unknown occupied resource")
    execution_path = folder / "execution-summary.json"
    if execution_path.exists():
        execution = read(execution_path)
        check(execution["status"] == "completed", "request execution failed")
        check(all(r["completed"] and r["num_processed_tokens"] == r["num_prefill_tokens"] + r["num_decode_tokens"]
                  for r in execution["requests"]), "request tokens/completion")
        for stage in execution["stages"]:
            check(stage["completion_count"] == 1, "StageEnd count")
            graph = graphs.get(stage.get("graph_id"))
            if graph and stage.get("expanded_service_s") is not None:
                total = math.fsum(t["cost"]["duration_s"] for t in graph["tasks"])
                check(abs(total-stage["expanded_service_s"]) <= TOLERANCE, "final expanded cost settlement")
    return dict(folder=str(folder), graphs=len(graphs), tasks=len(tasks), errors=errors, passed=not errors)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", type=Path, required=True)
    args = p.parse_args()
    reports = []
    for timeline in sorted(args.run.rglob("timeline.csv")):
        folder = timeline.parent
        if any("pytest" in part for part in folder.parts):
            continue
        if not all((folder / name).exists() for name in ("summary.json", "resource_timeline.csv")):
            continue
        try:
            reports.append(audit(folder))
        except Exception as exc:
            reports.append(dict(folder=str(folder), passed=False, errors=[repr(exc)], graphs=0, tasks=0))
    result = dict(passed=bool(reports) and all(r["passed"] for r in reports), cli_outputs=len(reports),
                  graphs=sum(r["graphs"] for r in reports), tasks=sum(r["tasks"] for r in reports), cases=reports)
    (args.run / "independent-output-audit.json").write_text(json.dumps(result, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "cases"}))
    raise SystemExit(0 if result["passed"] else 1)
