"""Run phase-5 original CLI, resource and reference-data acceptance."""
import argparse
import csv
import importlib.metadata
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.dag_phase4.main import (
    SCENARIOS, cli_command, compare, hashes, run_cli, sources, synthetic_profiles,
    write_csv, write_json,
)
from accuracy import evaluate

MODES = ("legacy", "dag_coarse", "dag_expanded")
METRICS = ("request_e2e_time", "prefill_e2e_time", "decode_time_execution_plus_preemption_normalized")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_metrics(folder):
    with (folder / "request_metrics.csv").open(encoding="utf-8") as stream:
        return [{field: float(row[field]) for field in METRICS} for row in csv.DictReader(stream)]


def graph_checks(folder, run, tp, pp):
    summary = read_json(folder / "summary.json")
    definitions = {graph["graph_id"]: graph for graph in
                   (read_json(path) for path in (folder / "graphs").glob("*.graph.json"))}
    with (folder / "timeline.csv").open(encoding="utf-8") as stream:
        tasks = {(row["graph_id"], row["task_id"]): row for row in csv.DictReader(stream)}
    fees = dependencies = communication = True
    for stage in run["stages"]:
        gid = stage["graph_id"]
        graph = definitions[gid]
        specs = graph["tasks"]
        fees &= (all(task["kind"] != "coarse" for task in specs)
                 and compare(math.fsum(t["cost"]["duration_s"] for t in specs), stage["predicted_duration_s"]))
        dependencies &= all(float(tasks[gid, a]["end_at_s"]) <= float(tasks[gid, b]["start_at_s"])
                            for a, b in graph["edges"])
        tp_ops = [t for t in specs if t["metadata"].get("communication_type") == "tp"]
        pp_ops = [t for t in specs if t["metadata"].get("communication_type") == "pp"]
        layers = {t["metadata"]["layer"] for t in specs if t["metadata"]["op"] == "attention.compute"}
        communication &= (len(tp_ops) == (2 * len(layers) if tp > 1 else 0)
                          and all(len(t["placement"]["device_ids"]) == tp for t in tp_ops)
                          and len(pp_ops) == int(stage["stage_id"] < pp - 1)
                          and all(len(t["metadata"]["rank_pairs"]) == tp for t in pp_ops))
    return {
        "fees_match": fees, "dependencies_hold": dependencies, "communication_matches": communication,
        "graph_count_matches": len(definitions) == len(run["stages"]) == len(summary["graphs"]) > 0,
        "all_tasks_once": bool(tasks) and all(r["completion_count"] == "1" for r in tasks.values()),
        "terminal_once": all(g["terminal_callback_count"] == 1 for g in summary["graphs"]),
        "capacity_validated": summary["resource_capacity_validated"],
        "queue_drained": summary["pending_event_count"] == 0,
        "final_usage_zero": all(r["used"] == 0 for r in summary["resource_capacity"].values()),
    }


def run_comparisons(output):
    profiles = output / "synthetic-profiles"
    synthetic_profiles(profiles)
    compatibility = output / "synthetic-pp-resource-config.json"
    write_json(compatibility, {"independent_comm": ["pp"]})
    reports, request_rows, stage_rows, metric_rows = [], [], [], []
    for name, pp, replicas, tp, requests in SCENARIOS:
        folder = output / name
        folder.mkdir()
        trace = folder / "requests.csv"
        write_csv(trace, [dict(arrived_at=t, num_prefill_tokens=p, num_decode_tokens=d)
                          for t, p, d in requests])
        runs = {}
        for mode in MODES:
            destination = folder / mode
            command = cli_command(mode, destination, profiles, trace, pp=pp, replicas=replicas, tp=tp)
            if mode == "dag_expanded" and pp > 1:
                command += ["--dag_resource_config", str(compatibility)]
            runs[mode] = run_cli(command, destination)
        old, old_folder = runs["legacy"]
        reference_metrics = read_metrics(old_folder)
        for mode in MODES[1:]:
            run, run_folder = runs[mode]
            stages = [{key: row[key] for key in old["stages"][0]} for row in run["stages"]]
            metrics = read_metrics(run_folder)
            checks = {
                "requests_match": compare(old["requests"], run["requests"]),
                "stages_match": compare(old["stages"], stages),
                "final_time_matches": compare(old["final_time_s"], run["final_time_s"]),
                "metrics_match": len(metrics) == len(requests) and compare(reference_metrics, metrics),
                "completed": run["status"] == "completed" and len(run["requests"]) == len(requests)
                and all(r["completed"] and r["num_processed_tokens"] == p + d
                        for r, (_, p, d) in zip(run["requests"], requests)),
                "stage_end_once": bool(stages) and all(s["completion_count"] == 1 for s in stages),
            }
            if mode == "dag_expanded":
                checks.update(graph_checks(run_folder, run, tp, pp))
            reports.append(dict(scenario=name, mode=mode, passed=all(checks.values()), checks=checks))
            for a, b in zip(old["requests"], run["requests"]):
                request_rows.append(dict(scenario=name, mode=mode, request_id=a["id"],
                                         legacy_tokens=a["num_processed_tokens"], dag_tokens=b["num_processed_tokens"],
                                         legacy_completed_at_s=a["completed_at"], dag_completed_at_s=b["completed_at"],
                                         passed=compare(a, b)))
            for a, b in zip(old["stages"], stages):
                stage_rows.append(dict(scenario=name, mode=mode, batch_stage_id=a["batch_stage_id"],
                                       legacy_start_s=a["start_at_s"], dag_start_s=b["start_at_s"],
                                       legacy_end_s=a["end_at_s"], dag_end_s=b["end_at_s"], passed=compare(a, b)))
            for index, (a, b) in enumerate(zip(reference_metrics, metrics)):
                metric_rows.append(dict(scenario=name, mode=mode, request_index=index, passed=compare(a, b),
                                        **{f"legacy_{k}": v for k, v in a.items()},
                                        **{f"dag_{k}": v for k, v in b.items()}))
        if pp > 1:
            destination = output / "pipeline-contention" / "dag_expanded"
            command = cli_command("dag_expanded", destination, profiles, trace, pp=pp, replicas=replicas, tp=tp)
            run, run_folder = run_cli(command, destination)
            checks = graph_checks(run_folder, run, tp, pp)
            checks.update(
                pp_contention_observed=any(stage["graph_resource_wait_s"] > 0 for stage in run["stages"]),
                completed=run["status"] == "completed"
                and len(run["requests"]) == len(requests)
                and all(r["completed"] and r["num_processed_tokens"] == p + d
                        for r, (_, p, d) in zip(run["requests"], requests)),
            )
            reports.append(dict(scenario="pipeline-contention", mode="dag_expanded",
                                passed=all(checks.values()), checks=checks))
    write_csv(output / "request-comparison.csv", request_rows)
    write_csv(output / "stage-comparison.csv", stage_rows)
    write_csv(output / "metrics-comparison.csv", metric_rows)
    return reports


def run_regression(output):
    command = [sys.executable, "-m", "pytest", "tests/test_dag_phase1_contracts.py", "tests/dag",
               "-q", "-p", "no:cacheprovider", "--basetemp", str(output / "pytest-tmp"),
               "--junitxml", str(output / "pytest.xml")]
    env = dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", PHASE5_PROBE_OUTPUT=str(output / "probes"))
    write_json(output / "pytest-command.json", command)
    with (output / "pytest.log").open("w", encoding="utf-8") as log:
        return subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT).returncode


def source_hashes():
    return sources() | hashes(ROOT, {
        path for folder in ("scripts/dag_phase1", "scripts/dag_phase5", "configs/dag", "docs/dag/phase5", "tests/fixtures/dag")
        for path in (ROOT / folder).rglob("*") if path.is_file() and "__pycache__" not in path.parts
    })


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--wsl-build", type=Path, help="verified WSL backend build evidence directory")
    parser.add_argument("--refine-from", type=Path, help="prior WSL run with a regressed 64 MiB validation sample")
    args = parser.parse_args(argv)
    if args.refine_from and not args.wsl_build:
        parser.error("--refine-from requires --wsl-build")
    output = (ROOT / args.output).resolve()
    if (output.parent != ROOT / "results/dag/phase5"
            or not re.fullmatch(r"\d{8}-phase5-[a-z0-9-]+-\d{2,}", output.name)):
        parser.error("output must be results/dag/phase5/YYYYMMDD-phase5-<purpose>-NN")
    try:
        output.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        parser.error(str(exc))
    started = time.perf_counter()
    manifest = dict(command_argv=[sys.executable, str(Path(__file__)), *(sys.argv[1:] if argv is None else argv)],
                    python=sys.version, seed=42)
    report = dict(functional_status="failed", accuracy_status="not_evaluated", profile_nature="synthetic")
    code = 1
    try:
        manifest["source_sha256"] = source_hashes()
        for key, command in (
            ("head", ["rev-parse", "HEAD"]), ("status", ["status", "--short", "--ignore-submodules=all"]),
            ("diff", ["diff", "--binary", "--ignore-submodules=all", "HEAD"]),
        ):
            result = subprocess.run(["git", *command], cwd=ROOT, capture_output=True, encoding="utf-8", errors="replace")
            manifest[f"git_{key}"] = dict(exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr)
        manifest["dependencies"] = {
            d.metadata["Name"]: importlib.metadata.version(d.metadata["Name"])
            for d in importlib.metadata.distributions()
        }
        collective_evidence = None
        if args.wsl_build:
            from collective_acceptance import evaluate_collectives
            prior = args.refine_from.resolve() if args.refine_from else None
            collective_evidence = evaluate_collectives(output, args.wsl_build.resolve(), prior)
        accuracy, inputs = evaluate(output, collective_evidence)
        manifest["input_sha256"] = hashes(ROOT, inputs)
        report["accuracy_status"] = accuracy["status"]
        report["accuracy_scope"] = accuracy["scope"]
        report["accuracy_validation_metrics"] = accuracy["validation_metrics"]
        report["primary_metric_status"] = accuracy["primary_metric_status"]
        report["checks"] = run_comparisons(output)
        report["pytest_exit_code"] = run_regression(output)
        if source_hashes() != manifest["source_sha256"]:
            raise RuntimeError("source files changed during acceptance")
        if not report["pytest_exit_code"] and all(row["passed"] for row in report["checks"]):
            report["functional_status"] = "passed"
            code = 0 if accuracy["status"] == "passed" else 2
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        write_json(output / "operation-error.json", dict(error=report["error"], traceback=traceback.format_exc()))
    report["exit_code"] = code
    write_json(output / "acceptance-report.json", report)
    manifest.update(exit_code=code, wall_time_s=time.perf_counter() - started)
    manifest["artifact_sha256"] = hashes(output, {
        path for path in output.rglob("*") if path.is_file()
        and not {"predictor-cache", "pytest-tmp"}.intersection(path.relative_to(output).parts)
    })
    write_json(output / "run-manifest.json", manifest)
    print(json.dumps(report))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
