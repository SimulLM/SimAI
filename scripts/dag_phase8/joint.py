"""Original CLI joint runs and checks derived independently from saved artifacts."""
import csv
import json
import math
from pathlib import Path
import sys

from scripts.dag_phase4.main import ROOT, cli_command, run_cli, write_csv, write_json


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def rows(path):
    with Path(path).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def command(destination, profiles, trace, config_dir=None):
    config_dir = config_dir or ROOT / "configs/dag/phase8"
    cmd = cli_command("dag_expanded", destination, profiles, trace, replicas=4)
    for option in ("--sarathi_scheduler_config_chunk_size", "--sarathi_scheduler_config_batch_size_cap"):
        index = cmd.index(option)
        del cmd[index:index + 2]
    cmd[cmd.index("--replica_scheduler_config_type") + 1] = "split_wise"
    cmd += ["--global_scheduler_config_type", "split_wise", "--replica_config_pd_node_ratio", "0.5",
            "--split_wise_replica_scheduler_config_batch_size_cap", "4",
            "--dag_pd_config", str(config_dir / "pd.json"),
            "--dag_moe_config", str(config_dir / "moe.json"),
            "--dag_resource_config", str(config_dir / "resources.json")]
    return [sys.executable, str(ROOT / "scripts/dag_phase8/profile_cli.py"),
            "--performance-output", str(destination / "performance.json"), *cmd[3:]]


def check_artifacts(folder, expected_requests, *, require_backpressure=False):
    execution, dag, pd = (read(folder / name) for name in
                         ("execution-summary.json", "summary.json", "pd-summary.json"))
    routing = read(folder / "moe-routing.json")["rounds"]
    kv = read(folder / "kv-events.json")
    timeline = {(r["graph_id"], r["task_id"]): r for r in rows(folder / "timeline.csv")}
    definitions = {g["graph_id"]: g for g in (read(path) for path in (folder / "graphs").glob("*.graph.json"))}
    checks = dict(
        requests_completed=execution["status"] == "completed" and len(execution["requests"]) == len(expected_requests)
            and all(r["completed"] and r["num_processed_tokens"] == p + d
                    for r, (_, p, d) in zip(execution["requests"], expected_requests)),
        terminal_once=all(g["terminal_callback_count"] == 1 for g in dag["graphs"]),
        stage_end_once=all(s["completion_count"] == 1 for s in execution["stages"]),
        capacities_valid=dag["resource_capacity_validated"] and all(v["used"] == 0 for v in pd["resource_capacity"].values()),
        queue_empty=dag["pending_event_count"] == 0,
        dependencies=all(float(timeline[gid, a]["end_at_s"]) <= float(timeline[gid, b]["start_at_s"])
                         for gid, graph in definitions.items() for a, b in graph["edges"]),
        kv_capacity_history=all(0 <= v["used"] <= v["capacity"] for e in kv for v in e["usage"].values()),
        kv_handles_released=not pd["cleanup_errors"] and all(m["state"] == "COMPLETED" and not any(
            m[key] for key in ("source_reservations", "destination_reservations", "pins")) for m in pd["migrations"]),
        both_ep_domains={r["group"] for r in routing} == {"prefill", "decode"},
        conservation=bool(routing) and all(sum(r["expert_counts"].values()) ==
            sum(r["routing"]["tokens_by_source"].values()) * r["routing"]["top_k"] == len(r["routing"]["assignments"])
            for r in routing),
        gpu_nic_wait_observed=any(float(r["resource_wait_s"]) > 0 for r in timeline.values()),
        final_service_settlement=all(math.isclose(s["expanded_service_s"],
            math.fsum(t["cost"]["duration_s"] for t in definitions[s["graph_id"]]["tasks"]),
            rel_tol=1e-12, abs_tol=1e-15) for s in execution["stages"]),
        zero_legacy_mlp_charge=not any(t["metadata"].get("op") in ("mlp.compute", "moe.compute", "moe.ep")
            for g in definitions.values() for t in g["tasks"]),
    )
    checks.update(decode_after_kv_ready=True, source_retained=True, route_consistent=True,
                  phase_placement=True, transfer_cost=True, commit_capacity_unchanged=True)
    for before, event in zip(kv, kv[1:]):
        if event["operation"] == "commit":
            resource = event["resource_id"]
            checks["commit_capacity_unchanged"] &= before["usage"][resource]["used"] == event["usage"][resource]["used"]
    for migration in pd["migrations"]:
        rid = migration["request_id"]
        starts = [s["start_at_s"] for s in execution["stages"] if s["stage_id"] == 0 and
                  s["replica_id"] == migration["destination"] and rid in map(str, s["request_ids"])]
        if not migration["graph_id"]:
            checks["decode_after_kv_ready"] &= not starts
            continue
        transfer_ends = [float(r["end_at_s"]) for (gid, _), r in timeline.items()
                         if gid in migration["graph_ids"] and r["kind"] == "comm"]
        checks["decode_after_kv_ready"] &= bool(starts) and (
            max(transfer_ends) <= migration["kv_ready_at_s"] <= min(starts) == migration["first_decode_start_s"])
        source_releases = [e["time_s"] for e in kv if e["request_id"] == rid and e["operation"] == "release"
                           and e["resource_id"].startswith(f"kv:gpu:{migration['source']}:")]
        checks["source_retained"] &= bool(source_releases) and min(source_releases) >= max(transfer_ends)
    for record in routing:
        allowed = {f"gpu:{i}:0:0" for i in ((0, 1) if record["group"] == "prefill" else (2, 3))}
        checks["phase_placement"] &= set(record["matrix"]) == allowed and all(set(row) == allowed for row in record["matrix"].values())
        for task in definitions[record["graph_id"]]["tasks"]:
            metadata = task["metadata"]
            if metadata.get("layer") != record["routing"]["layer"] or not metadata.get("op", "").startswith("expert."):
                continue
            checks["route_consistent"] &= (metadata["routing_digest"] == record["routing_digest"] and
                metadata["assignments"] == record["expert_counts"][metadata["expert"]] and
                set(task["placement"]["device_ids"]).issubset(allowed))
    for graph in definitions.values():
        for task in graph["tasks"]:
            m = task["metadata"]
            if m.get("op") == "pd.transfer":
                checks["transfer_cost"] &= math.isclose(task["cost"]["duration_s"], m["latency_s"] +
                    m["wire_bytes"] / m["bandwidth_bytes_per_s"], rel_tol=1e-12, abs_tol=1e-15)
    maximum_wait = max((m["capacity_wait_s"] or 0 for m in pd["migrations"]), default=0)
    communication_wait = any(r["kind"] == "comm" and "fabric" in r["demands"] and
                             float(r["resource_wait_s"]) > 0 for r in timeline.values())
    if len(expected_requests) > 1:
        checks["communication_contention_observed"] = communication_wait
    if require_backpressure:
        checks["backpressure_observed"] = maximum_wait > 0
    return dict(passed=all(checks.values()), checks=checks, request_count=len(execution["requests"]),
                task_count=dag["task_count"], event_count=len(read(folder / "event_trace.json")),
                dag_event_count=dag["event_count"], event_queue_peak=dag["event_queue_peak"],
                graph_count=len(dag["graphs"]), routing_count=len(routing),
                maximum_capacity_wait_s=maximum_wait, communication_wait_observed=communication_wait,
                simulated_final_time_s=execution["final_time_s"])


def run_case(output, profiles, name, requests, *, require_backpressure=False, config_dir=None):
    folder = output / name
    folder.mkdir()
    trace = folder / "requests.csv"
    write_csv(trace, [dict(arrived_at=t, num_prefill_tokens=p, num_decode_tokens=d) for t, p, d in requests])
    _, result = run_cli(command(folder / "cli", profiles, trace, config_dir), folder / "cli")
    report = check_artifacts(result, requests, require_backpressure=require_backpressure)
    report.update(name=name, output=str(result.relative_to(output)), **read(folder / "cli/performance.json"))
    write_json(folder / "checks.json", report)
    return report
