"""Original-CLI same-cost experiment isolating shared-endpoint DAG resource waits."""
import argparse
import csv
from datetime import datetime
from hashlib import sha256
import importlib.metadata
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "vidur-alibabacloud")]
from scripts.dag_phase4.main import cli_command, hashes, run_cli, synthetic_profiles, write_csv
from scripts.dag_phase8.capture_cost_cli import FIELDS

SPEC = ROOT / "configs/dag/phase8/mechanism-experiment.json"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+"\n", encoding="utf-8", newline="\n")


def option(command, name, value):
    if name in command:
        command[command.index(name)+1] = str(value)
    else:
        command.extend((name, str(value)))


def source_hashes():
    paths = {p for name in ("schemas/dag", "vidur-alibabacloud/vidur", "scripts/dag_phase4", "scripts/dag_phase8")
             for p in (ROOT / name).rglob("*") if p.is_file() and p.suffix in (".py", ".json") and "__pycache__" not in p.parts}
    paths.add(SPEC)
    return hashes(ROOT, paths)


def command(mode, folder, profiles, trace, replicas, resources=None):
    cmd = cli_command(mode, folder / "cli", profiles, trace, pp=2, replicas=replicas, tp=1)
    for key, value in {"--global_scheduler_config_type": "round_robin",
                       "--sarathi_scheduler_config_batch_size_cap": 2,
                       "--sarathi_scheduler_config_chunk_size": 64,
                       "--random_forrest_execution_time_predictor_config_prediction_max_prefill_chunk_size": 64}.items():
        option(cmd, key, value)
    if resources:
        # Deliberately identical configuration argument: legacy retains its
        # original aggregate timing path, which does not enforce endpoint permits.
        option(cmd, "--dag_resource_config", resources)
    return [sys.executable, str(ROOT / "scripts/dag_phase8/capture_cost_cli.py"),
            "--capture-output", str(folder / "predictor-costs.json"), *cmd[3:]]


def observed_costs(path):
    result = read(path)
    if not result["snapshot_only"]:
        raise ValueError("invalid cost observation")
    return result["observations"]


def verify_cost(cost):
    if set(cost["components_ms"]) != set(FIELDS) or cost["layers"] != 16:
        raise ValueError("unsupported component contract")
    if any(not math.isfinite(v) or v < 0 for v in cost["components_ms"].values()):
        raise ValueError("nonfinite/negative component cost")
    fields = cost["components_ms"]
    layer = sum(fields[name] for name in FIELDS[:14])
    # FIELDS includes attention/MLP all-reduces once each; TP1 requires zero.
    if fields["attention_all_reduce_time"] != 0 or fields["mlp_all_reduce_time"] != 0:
        raise ValueError("this experiment requires TP1")
    total = (layer * 16 + sum(fields[name] for name in FIELDS[14:])) * 1e-3
    if not math.isclose(total, cost["total_s"], rel_tol=1e-12, abs_tol=1e-15):
        raise ValueError("component sum differs from aggregate predictor service")


def prepare(output):
    output.mkdir(parents=True, exist_ok=False)
    spec = read(SPEC)
    save(output / "experiment.json", spec)
    profiles = output / "profiles"
    synthetic_profiles(profiles)
    # Freeze a constrained logical 10Gb/s link profile before observing results.
    with (profiles / "network.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    for row in rows:
        row["time_stats.send_recv.median"] = 1000 * (spec["network_profile"]["latency_s"] +
            int(row["size"]) / spec["network_profile"]["bandwidth_bytes_per_s"])
    write_csv(profiles / "network.csv", rows)
    save(profiles / "network-provenance.json", dict(nature="synthetic", **spec["network_profile"],
        actual_service="Frozen RandomForrest predictor outputs, identical for reference/legacy/DAG; no fit"))
    for case in spec["cases"]:
        folder = output / "cases" / case["name"]
        folder.mkdir(parents=True)
        save(folder / "case.json", case)
        write_csv(folder / "requests.csv", [dict(arrived_at=i*case["arrival_gap_s"], num_prefill_tokens=tokens,
            num_decode_tokens=1) for i, tokens in enumerate(case["tokens"])])
        endpoints = {f"gpu:{i}:{stage}:0": "fabric" if case["endpoint"] == "shared" else f"nic:{i}"
                     for i in range(len(case["tokens"])) for stage in (0, 1)}
        save(folder / "resources.json", dict(endpoints=endpoints, independent_comm=[]))
    # Cost-only observations are from isolated requests: no DAG import, no
    # reference use of any probe start/end times or request completion metrics.
    probe = output / "cost-probe"
    probe.mkdir()
    tokens = sorted({token for case in spec["cases"] for token in case["tokens"]})
    write_csv(probe / "requests.csv", [dict(arrived_at=i*.1, num_prefill_tokens=token, num_decode_tokens=1)
                                       for i, token in enumerate(tokens)])
    print("Probing unmodified predictor service costs on isolated requests", flush=True)
    _, _ = run_cli(command("legacy", probe, profiles, probe / "requests.csv", 1), probe / "cli")
    observations = observed_costs(probe / "predictor-costs.json")
    contract = dict(schema_version="1.0", calibration_used=False, tokens={str(t): {} for t in tokens},
                    cost_source="Unmodified predictor return values; no execution timestamps")
    for observation in observations:
        [token] = observation["tokens"]
        key = str(int(token))
        stage = str(observation["stage"])
        if stage in contract["tokens"][key]:
            raise ValueError("cost probe unexpectedly produced multiple iterations/batches")
        verify_cost(observation["cost"])
        contract["tokens"][key][stage] = observation["cost"]
    if any(set(stages) != {"0", "1"} for stages in contract["tokens"].values()):
        raise ValueError("cost probe did not produce a complete two-stage contract")
    save(output / "cost-contract.json", contract)
    for case in spec["cases"]:
        folder = output / "cases" / case["name"]
        cmd = [sys.executable, str(ROOT / "scripts/dag_phase8/queue_reference.py"),
               "--case", str(folder / "case.json"), "--cost-contract", str(output / "cost-contract.json"),
               "--output", str(folder / "reference.json")]
        save(folder / "reference-command.json", cmd)
        subprocess.run(cmd, cwd=ROOT, check=True)
    frozen = {p for name in ("profiles", "cases") for p in (output / name).rglob("*") if p.is_file()}
    frozen.update((output / "experiment.json", output / "cost-contract.json"))
    save(output / "experiment-freeze.json", dict(phase="before_validation_cli_execution", fitted_parameters=0,
        input_sha256=hashes(output, frozen), queue_reference_source_sha256=digest(ROOT / "scripts/dag_phase8/queue_reference.py")))
    return spec


def check_frozen(output):
    for name, value in read(output / "experiment-freeze.json")["input_sha256"].items():
        if digest(output / name) != value:
            raise ValueError(f"frozen input/reference changed: {name}")


def run_case(output, case):
    folder = output / "cases" / case["name"]
    contract = read(output / "cost-contract.json")
    references = {r["request_id"]: r for r in read(folder / "reference.json")["requests"]}
    runs = {}
    checks = {}
    for mode in ("legacy", "dag_expanded"):
        print(f"Running {case['name']}: {mode}", flush=True)
        destination = folder / mode
        destination.mkdir()
        execution, native = run_cli(command(mode, destination, output / "profiles", folder / "requests.csv",
            len(case["tokens"]), folder / "resources.json"), destination / "cli")
        observations = observed_costs(destination / "predictor-costs.json")
        if len(observations) != 2 * len(case["tokens"]):
            raise ValueError("unexpected batch count, chunking or Decode iteration")
        for observation in observations:
            [rid] = observation["request_ids"]
            [token] = observation["tokens"]
            if int(token) != case["tokens"][rid] or observation["replica"] != rid:
                raise ValueError("request placement differs from the independent reference")
            expected = contract["tokens"][str(int(token))][str(observation["stage"])]
            if observation["cost"] != expected:
                raise ValueError("reference/legacy/DAG costs differ")
        checks[mode + "_costs_equal_frozen_contract"] = True
        if execution["status"] != "completed" or len(execution["requests"]) != len(case["tokens"]):
            raise ValueError("CLI did not complete every request")
        if mode == "dag_expanded":
            summary = read(native / "summary.json")
            if not summary["resource_capacity_validated"] or summary["pending_event_count"] != 0:
                raise ValueError("DAG resource/queue checks failed")
            if any(v["used"] != 0 for v in summary["resource_capacity"].values()):
                raise ValueError("DAG resources leaked")
            with (native / "timeline.csv").open(encoding="utf-8", newline="") as stream:
                timeline = list(csv.DictReader(stream))
            pp_rows = [r for r in timeline if r["task_id"] == "pipeline.send_recv"]
            if len(pp_rows) != len(case["tokens"]):
                raise ValueError("missing PP transfer tasks")
            for graph in (read(p) for p in (native / "graphs").glob("*.graph.json")):
                stage = next(s for s in execution["stages"] if s["graph_id"] == graph["graph_id"])
                if not math.isclose(math.fsum(t["cost"]["duration_s"] for t in graph["tasks"]),
                                    stage["predicted_duration_s"], abs_tol=1e-12):
                    raise ValueError("DAG task costs changed the aggregate service")
            for row in pp_rows:
                stage = next(s for s in execution["stages"] if s["graph_id"] == row["graph_id"])
                [rid] = stage["request_ids"]
                ref = references[rid]
                for key, field in (("ready_at_s", "communication_ready_s"), ("start_at_s", "communication_start_s"),
                                   ("end_at_s", "communication_end_s"), ("resource_wait_s", "resource_wait_s")):
                    if not math.isclose(float(row[key]), ref[field], rel_tol=1e-10, abs_tol=1e-12):
                        raise ValueError(f"DAG transfer {key} differs from the independent queue reference")
            checks["transfer_ready_start_end_wait_match_reference"] = True
            checks["final_resources_and_events_clear"] = True
        runs[mode] = {r["id"]: r for r in execution["requests"]}
    rows = []
    for rid, tokens in enumerate(case["tokens"]):
        ref = references[rid]
        row = dict(case=case["name"], role=case["role"], endpoint=case["endpoint"], request_id=rid, prefill_tokens=tokens,
                   arrived_at_s=ref["arrived_at_s"], reference_e2e_s=ref["request_e2e_s"], reference_wait_s=ref["resource_wait_s"])
        for mode in runs:
            request = runs[mode][rid]
            if not request["completed"] or request["num_processed_tokens"] != tokens+1:
                raise ValueError("request completion/token count mismatch")
            value = request["completed_at"] - request["arrived_at"]
            row[mode + "_e2e_s"] = value
            row[mode + "_absolute_error_s"] = abs(value-ref["request_e2e_s"])
            row[mode + "_relative_error"] = abs(value-ref["request_e2e_s"])/ref["request_e2e_s"]
        difference = row["legacy_absolute_error_s"] - row["dag_expanded_absolute_error_s"]
        row["outcome"] = "tied" if abs(difference) <= 1e-12 else ("improved" if difference > 0 else "regressed")
        row["dag_matches_reference"] = row["dag_expanded_absolute_error_s"] <= 1e-12
        rows.append(row)
    checks["all_request_e2e_match_reference"] = all(r["dag_matches_reference"] for r in rows)
    if case["role"] == "control":
        checks["control_has_no_reference_wait"] = all(r["reference_wait_s"] == 0 for r in rows)
        checks["legacy_control_matches_reference"] = all(r["legacy_absolute_error_s"] <= 1e-12 for r in rows)
    save(folder / "checks.json", dict(passed=all(checks.values()), checks=checks))
    return rows, all(checks.values())


def summarize(rows):
    results = []
    for name in dict.fromkeys(r["case"] for r in rows):
        group = [r for r in rows if r["case"] == name]
        results.append(dict(case=name, role=group[0]["role"], requests=len(group),
            legacy_mean_relative_error=math.fsum(r["legacy_relative_error"] for r in group)/len(group),
            dag_mean_relative_error=math.fsum(r["dag_expanded_relative_error"] for r in group)/len(group),
            max_reference_wait_s=max(r["reference_wait_s"] for r in group),
            **{name: sum(r["outcome"] == name for r in group) for name in ("improved", "tied", "regressed")}))
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prepare-only", action="store_true", help="freeze inputs, probe costs and generate independent references")
    parser.add_argument("--run-prepared", action="store_true", help="run an already prepared experiment")
    args = parser.parse_args(argv)
    if args.prepare_only and args.run_prepared:
        parser.error("choose only one preparation option")
    output = (ROOT / args.output).resolve()
    if output == ROOT / "results/dag/phase8" or not output.is_relative_to(ROOT / "results/dag/phase8"):
        parser.error("output must be below results/dag/phase8")
    started = time.perf_counter()
    if not args.run_prepared:
        spec = prepare(output)
    else:
        spec = read(output / "experiment.json")
    if args.prepare_only:
        print(f"Prepared references and frozen zero-fit cost contract: {output}")
        return 0
    if (output / "mechanism-report.json").exists():
        parser.error("refusing to overwrite an executed experiment")
    before = source_hashes()
    check_frozen(output)
    rows, cases = [], []
    for case in spec["cases"]:
        part, passed = run_case(output, case)
        rows.extend(part)
        cases.append(dict(case=case["name"], passed=passed))
        check_frozen(output)
    if source_hashes() != before:
        raise ValueError("source changed during validation")
    summaries = summarize(rows)
    validation = [r for r in rows if r["role"] == "validation"]
    legacy = math.fsum(r["legacy_relative_error"] for r in validation)/len(validation)
    dag = math.fsum(r["dag_expanded_relative_error"] for r in validation)/len(validation)
    status = "passed" if all(c["passed"] for c in cases) and legacy-dag>1e-12 else "not_improved"
    report = dict(status=status, scope=spec["scope"], reference_type="independent_decimal_fcfs_queue",
        primary_metric=spec["primary_metric"], validation_requests=len(validation), control_requests=len(rows)-len(validation),
        legacy_mean_relative_error=legacy, dag_mean_relative_error=dag,
        outcomes={name: sum(r["outcome"]==name for r in validation) for name in ("improved", "tied", "regressed")},
        same_cost_verified=True, fitted_parameters=0, calibration_used=False,
        hardware_accuracy_claim=False, overall_project_acceptance="pending", cases=cases,
        limitations=spec["limitations"], wall_time_s=time.perf_counter()-started)
    write_csv(output / "request-comparison.csv", rows)
    write_csv(output / "case-summary.csv", summaries)
    save(output / "mechanism-report.json", report)
    save(output / "run-manifest.json", dict(source_sha256=before, experiment_freeze_sha256=digest(output / "experiment-freeze.json"),
        command=[sys.executable, *sys.argv], python=sys.version,
        dependencies={d.metadata["Name"]: d.version for d in importlib.metadata.distributions()},
        artifact_sha256=hashes(output, {p for p in output.rglob("*") if p.is_file()})))
    print(json.dumps(report, indent=2), flush=True)
    return 0 if status == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
