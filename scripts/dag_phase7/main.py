"""Archive dynamic MoE functional acceptance; missing real timing evidence exits 2."""
from __future__ import annotations

import argparse
from copy import deepcopy
import csv
import heapq
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import traceback
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vidur-alibabacloud"))

from scripts.dag_phase4.main import cli_command, hashes, run_cli, sources, synthetic_profiles, write_csv, write_json
from vidur.dag.expanded import ATTENTION, CPU_POST, CPU_PRE, MLP
from vidur.dag.expanded_trace import write_expanded_results
from vidur.dag.moe_host import DynamicMoeDagAdapter
from vidur.dag.trace import write_results
from vidur.entities import BatchStage, Request
from vidur.events.batch_stage_end_event import BatchStageEndEvent


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def rows(path):
    with Path(path).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def drain(events):
    queue = [(event._priority_number, event) for event in events]
    heapq.heapify(queue)
    ends = []
    while queue:
        _, event = heapq.heappop(queue)
        if isinstance(event, BatchStageEndEvent):
            ends.append(event)
        else:
            for successor in event.handle_event(None, None):
                heapq.heappush(queue, (successor._priority_number, successor))
    return ends


def controlled_probes(output):
    """Analytically checkable input; not a replacement for the original CLI run."""
    template = read_json(ROOT / "configs/dag/phase7/alternating.json")
    resource_template = read_json(ROOT / "configs/dag/phase7/resources.json")
    checks, results = [], []
    for pattern in ("balanced", "hotspot"):
        folder = output / "probes" / pattern
        folder.mkdir(parents=True)
        data, resources = deepcopy(template), deepcopy(resource_template)
        data["routing"]["patterns"] = [pattern]
        data["cost"].update(up_s_per_assignment=.001, down_s_per_assignment=.001,
                            dispatch_bytes_per_assignment=8, combine_bytes_per_assignment=8, latency_s=0)
        resources["endpoints"] = {"gpu:0:0:0": "nic0", "gpu:1:0:0": "nic1"}
        resources["independent_comm"] = ["ep"]
        write_json(folder / "moe-config.json", data)
        write_json(folder / "resources.json", resources)
        host = DynamicMoeDagAdapter([(0, 0), (1, 0)], 1, "vidur", "synthetic", resources, data)
        request = Request(0, 8, 4)
        request.on_batch_schedule(0)
        batch = SimpleNamespace(id=0, requests=[request], total_num_tokens=8,
                                num_prefill_tokens=8, num_decode_tokens=0)
        stage = BatchStage(0, 0, 0, 0, 0, [request], [8])
        fields = dict.fromkeys((*ATTENTION, *MLP, *CPU_PRE, *CPU_POST, "add_time",
                                "attention_all_reduce_time", "mlp_all_reduce_time",
                                "pipeline_parallel_communication_time"), 0)
        execution_time = SimpleNamespace(**fields, num_layers=1)
        events = host.submit_stage(0, 0, 0, True, batch, stage, on_stage_start=stage.on_schedule,
                                   execution_time=execution_time)
        end, = drain(events)
        host.now = end.time
        stage.on_stage_end(end.time)
        summary = write_results(folder, host)
        write_expanded_results(folder, host.executor)
        host.write_moe_results(folder)
        graph, = host.executor.graphs.values()
        experts = [t for t in graph.tasks.values() if t.spec.metadata.get("op", "").startswith("expert.")]
        results.append(dict(pattern=pattern, stage_end_s=end.time,
                            resource_wait_s=sum(t.resource_wait_s for t in experts),
                            expert_counts=host.rounds[0]["expert_counts"]))
        checks.append(dict(name="controlled_" + pattern, passed=(summary["resource_capacity_validated"]
                           and graph.callback_count == 1 and sum(host.rounds[0]["expert_counts"].values()) == 16)))
    checks.append(dict(name="controlled_hotspot_tail", passed=results[1]["stage_end_s"] > 1.9 * results[0]["stage_end_s"]))
    write_json(output / "controlled-results.json", results)
    return checks


def original_cli(output):
    profiles = output / "synthetic-profiles"
    synthetic_profiles(profiles)
    trace = output / "requests.csv"
    write_csv(trace, [dict(arrived_at=0, num_prefill_tokens=8, num_decode_tokens=4),
                      dict(arrived_at=0, num_prefill_tokens=8, num_decode_tokens=4)])
    destination = output / "original-cli"
    command = cli_command("dag_expanded", destination, profiles, trace, replicas=2)
    command[command.index("--sarathi_scheduler_config_batch_size_cap") + 1] = "1"
    command += ["--dag_moe_config", str(ROOT / "configs/dag/phase7/alternating.json"),
                "--dag_resource_config", str(ROOT / "configs/dag/phase7/resources.json")]
    summary, folder = run_cli(command, destination)
    dag = read_json(folder / "summary.json")
    routing = read_json(folder / "moe-routing.json")["rounds"]
    timeline = {(r["graph_id"], r["task_id"]): r for r in rows(folder / "timeline.csv")}
    costs = rows(folder / "cost-breakdown.csv")
    by_id = {graph["graph_id"]: graph for graph in
             (read_json(path) for path in (folder / "graphs").glob("*.graph.json"))}
    checks = dict(
        original_requests_complete=summary["status"] == "completed" and len(summary["requests"]) == 2
            and all(r["completed"] and r["num_processed_tokens"] == 12 for r in summary["requests"]),
        stage_end_once=bool(summary["stages"]) and all(s["completion_count"] == 1 for s in summary["stages"]),
        terminal_once=all(g["terminal_callback_count"] == 1 for g in dag["graphs"]),
        capacities_validated=dag["resource_capacity_validated"] and not dag["pending_event_count"]
            and all(r["used"] == 0 for r in dag["resource_capacity"].values()),
        multiple_rounds=bool(routing) and {r["routing"]["strategy"] for r in routing} == {"balanced", "hotspot"}
            and {r["routing"]["phase"] for r in routing} == {"prefill", "decode"},
        resource_contention=any(float(r["resource_wait_s"]) > 0 for r in timeline.values()),
        shared_nic_wait=any(r["kind"] == "comm" and float(r["resource_wait_s"]) > 0
            and "shared-ep-nic" in r["demands"] for r in timeline.values()),
        assignments_conserved=all(len(r["routing"]["assignments"]) ==
            sum(r["routing"]["tokens_by_source"].values()) * r["routing"]["top_k"] for r in routing),
        matrices_complete=all(len(r["matrix"]) == 2 and all(len(row) == 2 for row in r["matrix"].values())
            and sum(sum(row.values()) for row in r["matrix"].values()) == len(r["routing"]["assignments"]) for r in routing),
        all_dependencies=all(float(timeline[gid, a]["end_at_s"]) <= float(timeline[gid, b]["start_at_s"])
            for gid, graph in by_id.items() for a, b in graph["edges"]),
        final_service_settled=all(math.isclose(stage["expanded_service_s"],
            math.fsum(t["cost"]["duration_s"] for t in by_id[stage["graph_id"]]["tasks"]),
            rel_tol=1e-12, abs_tol=1e-15) for stage in summary["stages"]),
        removed_mlp_not_double_charged=not any(r["op"] in ("mlp.compute", "moe.compute", "moe.ep") for r in costs),
    )
    consistent = True
    for record in routing:
        graph = by_id[record["graph_id"]]
        layer = record["routing"]["layer"]
        specs = [task for task in graph["tasks"] if task["metadata"].get("layer") == layer
                 and task["metadata"].get("op", "").startswith("expert.")]
        consistent &= all(task["metadata"]["routing_digest"] == record["routing_digest"]
                          and task["metadata"]["assignments"] == record["expert_counts"][task["metadata"]["expert"]]
                          for task in specs)
    checks["same_routing_up_down"] = consistent
    chrome = read_json(folder / "moe-task-chrome.json")
    checks["task_chrome_trace"] = len(chrome["traceEvents"]) == len(timeline)
    write_json(output / "original-cli-checks.json", dict(output=str(folder.relative_to(output)), checks=checks,
                                                        request_count=2, stage_count=len(summary["stages"]),
                                                        routing_count=len(routing), task_count=len(timeline)))
    return [dict(name=name, passed=bool(value)) for name, value in checks.items()]


def source_hashes():
    return sources() | hashes(ROOT, {path for name in ("scripts/dag_phase7", "configs/dag/phase7", "docs/dag/phase7")
        for path in (ROOT / name).rglob("*") if path.is_file() and path.suffix in (".py", ".json", ".csv", ".md")})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    output = (ROOT / args.output).resolve()
    if (output.parent != ROOT / "results/dag/phase7" or
            not re.fullmatch(r"\d{8}-phase7-[a-z0-9-]+-\d{2,}", output.name)):
        parser.error("output must be results/dag/phase7/YYYYMMDD-phase7-<purpose>-NN")
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    manifest = dict(python=sys.version, seed=42, source_sha256=source_hashes())
    for key, command in (("head", ["rev-parse", "HEAD"]), ("status", ["status", "--short"]),
                         ("diff", ["diff", "--binary", "HEAD"])):
        result = subprocess.run(["git", *command], cwd=ROOT, capture_output=True, encoding="utf-8", errors="replace")
        manifest["git_" + key] = dict(exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr)
    report = dict(functional_status="failed", accuracy_status="blocked_missing_matched_moe_reference",
                  hardware_accuracy_claim=False, profile_nature="synthetic", checks=[])
    code = 1
    try:
        print("Running controlled balanced/hotspot probes", flush=True)
        report["checks"].extend(controlled_probes(output))
        print("Running original CLI with two requests and alternating routes", flush=True)
        report["checks"].extend(original_cli(output))
        print("Running phase 1-7 regression", flush=True)
        command = [sys.executable, "-m", "pytest", "tests/test_dag_phase1_contracts.py", "tests/dag", "-q",
                   "-p", "no:cacheprovider", "--basetemp", str(output / "pytest-tmp"),
                   "--junitxml", str(output / "pytest.xml")]
        write_json(output / "pytest-command.json", command)
        with (output / "pytest.log").open("w", encoding="utf-8") as log:
            report["pytest_exit_code"] = subprocess.run(command, cwd=ROOT,
                env=dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD="1"), stdout=log, stderr=subprocess.STDOUT).returncode
        if source_hashes() != manifest["source_sha256"]:
            raise RuntimeError("source changed during acceptance")
        if report["pytest_exit_code"] == 0 and all(check["passed"] for check in report["checks"]):
            report["functional_status"] = "passed"
            code = 2
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        write_json(output / "operation-error.json", dict(error=report["error"], traceback=traceback.format_exc()))
    report["exit_code"] = code
    write_json(output / "acceptance-report.json", report)
    write_json(output / "accuracy-report.json", dict(status=report["accuracy_status"], samples=[],
        reason="No matching per-expert and end-to-end MoE reference timing is available; synthetic timings cannot establish accuracy improvement.",
        required=["matched model/device/TP/PP/EP/dtype and expert-load profiles", "source-token-expert routes",
                  "independent per-round or request timing reference", "separate calibration and validation samples"]))
    manifest.update(exit_code=code, wall_time_s=time.perf_counter() - started)
    manifest["artifact_sha256"] = hashes(output, {p for p in output.rglob("*") if p.is_file()
        and not {"pytest-tmp", "predictor-cache"}.intersection(p.relative_to(output).parts)})
    write_json(output / "run-manifest.json", manifest)
    print(json.dumps(report), flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
