"""Archive original-CLI legacy/coarse compatibility runs using synthetic profiles."""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def write_csv(path, rows):
    with Path(path).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def synthetic_profiles(folder):
    """Small deterministic CI training data, explicitly NOT hardware measurements."""
    folder.mkdir()
    compute, attention, network, cpu = [], [], [], []
    operators = ("attn_pre_proj", "attn_post_proj", "mlp_up_proj", "mlp_down_proj",
                 "mlp_act", "input_layernorm", "post_attention_layernorm", "add")
    for tp in (1, 2):
        for tokens in (1, 2, 4, 8, 16, 32, 64):
            row = dict(n_head=32, n_kv_head=32, n_embd=4096, n_expanded_embd=11008,
                       use_gated_mlp=True, vocab_size=32768, num_tensor_parallel_workers=tp,
                       num_tokens=tokens)
            row.update({f"time_stats.{name}.median": (0.01 + tokens * 0.0001) / tp for name in operators})
            compute.append(row)
            for chunk in (0, tokens):
                attention.append(dict(n_embd=4096, n_q_head=32, n_kv_head=32, block_size=16,
                                      num_tensor_parallel_workers=tp, batch_size=min(tokens, 4),
                                      prefill_chunk_size=chunk, kv_cache_size=tokens,
                                      **{"time_stats.attn_kv_cache_save.median": 0.002 + tokens * 0.0001,
                                         "time_stats.attn_prefill.median": 0.003 + tokens * 0.0001,
                                         "time_stats.attn_decode.median": 0.004 + tokens * 0.0001}))
            for collective in ("send_recv", "all_reduce"):
                network.append(dict(collective=collective, num_workers=tp, devices_per_node=2,
                                    size=tokens * 4096 * 2,
                                    **{"time_stats.send_recv.median": 0.005 + tokens * 0.0001,
                                       "time_stats.all_reduce.median": 0.006 + tokens * 0.0001}))
    for batch in range(1, 9):
        cpu.append(dict(model_name="meta-llama/Llama-2-7b-hf", tensor_parallel_degree=1,
                        batch_size=batch, schedule_median=0.001, sampler_e2e_median=0.002,
                        prepare_inputs_e2e_median=0.003, process_model_outputs_median=0.004,
                        ray_comm_time_mean=0.005))
    for name, rows in (("compute.csv", compute), ("attention.csv", attention),
                       ("network.csv", network), ("cpu.csv", cpu)):
        write_csv(folder / name, rows)
    write_json(folder / "provenance.json", {"nature": "synthetic", "hardware_measurements": False,
               "purpose": "Exercise the unmodified RandomForrestExecutionTimePredictor training and inference path",
               "unit": "ms", "model_shape": "meta-llama/Llama-2-7b-hf", "generator": "scripts/dag_phase4/main.py"})


def cli_command(mode, output, profiles, trace, *, pp=1, replicas=1, tp=1):
    prefix = "--random_forrest_execution_time_predictor_config_"
    return [sys.executable, "-m", "vidur.main", "--execution_mode", mode,
            "--seed", "42", "--log_level", "error",
            "--cluster_config_num_replicas", str(replicas),
            "--replica_config_num_pipeline_stages", str(pp),
            "--replica_config_tensor_parallel_size", str(tp),
            "--replica_config_model_name", "meta-llama/Llama-2-7b-hf",
            "--replica_config_device", "a100", "--replica_config_network_device", "a100_pairwise_nvlink",
            "--request_generator_config_type", "trace_replay",
            "--trace_request_generator_config_trace_file", str(trace),
            "--trace_request_generator_config_max_tokens", "64",
            "--replica_scheduler_config_type", "sarathi", "--sarathi_scheduler_config_chunk_size", "16",
            "--sarathi_scheduler_config_batch_size_cap", "4",
            prefix + "backend", "vidur", prefix + "num_estimators", "3",
            prefix + "max_depth", "2", prefix + "min_samples_split", "2",
            prefix + "k_fold_cv_splits", "2", prefix + "num_training_job_threads", "1",
            prefix + "prediction_max_batch_size", "4", prefix + "prediction_max_tokens_per_request", "64",
            prefix + "prediction_max_prefill_chunk_size", "16", prefix + "simai_dir", str(output),
            prefix + "compute_input_file", str(profiles / "compute.csv"),
            prefix + "attention_input_file", str(profiles / "attention.csv"),
            prefix + "send_recv_input_file", str(profiles / "network.csv"),
            prefix + "all_reduce_input_file", str(profiles / "network.csv"),
            "--metrics_config_output_dir", str(output), "--metrics_config_cache_dir", str(output.parent / "predictor-cache"),
            "--metrics_config_write_metrics", "--no-metrics_config_store_plots",
            "--metrics_config_write_json_trace", "--metrics_config_enable_chrome_trace"]


def run_cli(command, folder):
    folder.mkdir(parents=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(ROOT / "vidur-alibabacloud"), str(ROOT), env.get("PYTHONPATH", "")))
    env["WANDB_MODE"] = "disabled"
    write_json(folder / "command.json", command)
    with (folder / "process.log").open("w", encoding="utf-8") as log:
        result = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    write_json(folder / "process-result.json", {"exit_code": result.returncode})
    if result.returncode:
        raise RuntimeError(f"original CLI exited {result.returncode}; see {folder / 'process.log'}")
    summaries = list(folder.glob("*/execution-summary.json"))
    if len(summaries) != 1:
        raise RuntimeError("original CLI failed to save exactly one execution summary")
    for name in ("event_trace.json", "chrome_trace.json"):
        json.loads((summaries[0].parent / name).read_text(encoding="utf-8"))
    return json.loads(summaries[0].read_text(encoding="utf-8")), summaries[0].parent


def compare(left, right, field=""):
    # Identity/counters are exact; only seconds have a fixed numerical tolerance.
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(compare(left[key], right[key], key) for key in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(compare(a, b, field) for a, b in zip(left, right))
    if field.startswith("num_") or field.endswith(("_id", "_ids", "_count")) or field == "id":
        return type(left) is type(right) and left == right
    if isinstance(left, float) or isinstance(right, float):
        return isinstance(left, (int, float)) and isinstance(right, (int, float)) and abs(left - right) <= 1e-12
    return type(left) is type(right) and left == right


def run_comparisons(output):
    profiles = output / "synthetic-profiles"
    synthetic_profiles(profiles)
    checks, request_rows, stage_rows, metric_rows = [], [], [], []
    for name, pp, replicas, tp, requests in (
        ("single", 1, 1, 1, [(0, 8, 4)]),
        ("batching", 1, 1, 1, [(0, 8, 4), (0, 12, 3), (0.001, 5, 2)]),
        ("pipeline", 2, 1, 1, [(0, 8, 4), (0, 12, 3), (0.001, 5, 2)]),
        ("replicas", 1, 2, 1, [(0, 8, 4), (0, 12, 3), (0.001, 5, 2)]),
        ("tensor_parallel", 1, 1, 2, [(0, 8, 4), (0, 12, 3)]),
    ):
        folder = output / name
        folder.mkdir()
        trace = folder / "requests.csv"
        write_csv(trace, [dict(arrived_at=t, num_prefill_tokens=p, num_decode_tokens=d) for t, p, d in requests])
        runs = {}
        for mode in ("legacy", "dag_coarse"):
            destination = folder / mode
            runs[mode] = run_cli(cli_command(mode, destination, profiles, trace, pp=pp, replicas=replicas, tp=tp), destination)
        old, old_folder = runs["legacy"]
        new, new_folder = runs["dag_coarse"]
        summary = json.loads((new_folder / "summary.json").read_text(encoding="utf-8"))
        metric_fields = ("request_e2e_time", "prefill_e2e_time", "decode_time_execution_plus_preemption_normalized")
        metric_runs = []
        for run_folder in (old_folder, new_folder):
            with (run_folder / "request_metrics.csv").open(encoding="utf-8") as stream:
                metric_runs.append([{field: float(row[field]) for field in metric_fields}
                                    for row in csv.DictReader(stream)])
        metric_passed = (len(metric_runs[0]) == len(metric_runs[1]) == len(requests)
                         and all(math.isfinite(v) for rows in metric_runs for row in rows for v in row.values())
                         and compare(*metric_runs))
        invariants = {
            "requests_equal": compare(old["requests"], new["requests"]),
            "stages_equal": compare(old["stages"], new["stages"]),
            "final_time_equal": compare(old["final_time_s"], new["final_time_s"]),
            "all_requests_completed": len(new["requests"]) == len(requests) and all(r["completed"] for r in new["requests"]),
            "expected_tokens": all(r["num_processed_tokens"] == p + d for r, (_, p, d) in zip(new["requests"], requests)),
            "stage_end_once": bool(new["stages"]) and all(s["completion_count"] == 1 for s in new["stages"]),
            "terminal_once": len(summary["graphs"]) == len(new["stages"])
                and all(g["terminal_callback_count"] == 1 for g in summary["graphs"]),
            "capacity_validated": summary["resource_capacity_validated"],
            "final_usage_zero": all(r["used"] == 0 for r in summary["resource_capacity"].values()),
            "queue_drained": summary["pending_event_count"] == 0,
            "host_status_completed": old["status"] == new["status"] == "completed",
            "request_metrics_equal": metric_passed,
        }
        checks.append({"name": name, "passed": all(invariants.values()), "checks": invariants,
                       "request_count": len(requests), "stage_count": len(new["stages"]),
                       "legacy_final_time_s": old["final_time_s"], "dag_final_time_s": new["final_time_s"],
                       "pp": pp, "tp": tp, "replicas": replicas})
        for a, b in zip(old["requests"], new["requests"]):
            request_rows.append(dict(scenario=name, request_id=b["id"], legacy_tokens=a["num_processed_tokens"],
                                     dag_tokens=b["num_processed_tokens"], legacy_completed_at_s=a["completed_at"],
                                     dag_completed_at_s=b["completed_at"], passed=compare(a, b)))
        for a, b in zip(old["stages"], new["stages"]):
            stage_rows.append(dict(scenario=name, batch_stage_id=b["batch_stage_id"], replica_id=b["replica_id"],
                                   stage_id=b["stage_id"], legacy_start_s=a["start_at_s"], dag_start_s=b["start_at_s"],
                                   legacy_end_s=a["end_at_s"], dag_end_s=b["end_at_s"], passed=compare(a, b)))
        for index, (a, b) in enumerate(zip(*metric_runs)):
            row = dict(scenario=name, request_index=index)
            for field in metric_fields:
                row["legacy_" + field] = a[field]
                row["dag_" + field] = b[field]
            row["passed"] = compare(a, b)
            metric_rows.append(row)
    write_csv(output / "request-comparison.csv", request_rows)
    write_csv(output / "stage-comparison.csv", stage_rows)
    write_csv(output / "metrics-comparison.csv", metric_rows)
    return checks


def run_host_probes(output):
    """Save observed delay/failure behavior independently of CLI compatibility."""
    from types import SimpleNamespace
    from schemas.dag.v1.contracts import ResourceDemand
    from vidur.dag.host import CoarseDagAdapter
    from vidur.dag.trace import write_results
    from vidur.events.batch_stage_end_event import BatchStageEndEvent

    checks = []
    for name in ("resource_delay", "zero_duration", "graph_failure"):
        folder = output / name
        folder.mkdir()
        adapter = CoarseDagAdapter([(1, 0)])
        batch = SimpleNamespace(id=1, requests=[SimpleNamespace(id=1)])
        stage = SimpleNamespace(execution_time=0 if name == "zero_duration" else 2)
        manager = adapter.executor._resources
        held = None
        if name == "resource_delay":
            held = manager.try_acquire(("external", "holder"), (ResourceDemand("stage:1:0", 1, "permits"),))
        events = adapter.submit_stage(0, 1, 0, True, batch, stage)
        if held is not None:
            assert not events
            manager.release(held, 5)
            events = adapter._wrap(adapter.executor.dispatch(5))
        ends, observed_error = [], None
        if name == "graph_failure":
            graph_id, = adapter.executor.graphs
            failure, = adapter.executor.fail_task(graph_id, "coarse", 1, "controlled phase4 failure")
            try:
                adapter.handle(failure)
            except RuntimeError as exc:
                observed_error = str(exc)
        else:
            import heapq
            queue = [(e._priority_number, e) for e in events]
            heapq.heapify(queue)
            while queue:
                _, event = heapq.heappop(queue)
                adapter.now = event.time
                if isinstance(event, BatchStageEndEvent):
                    ends.append(event.time)
                else:
                    for successor in event.handle_event(None, None):
                        heapq.heappush(queue, (successor._priority_number, successor))
        summary = write_results(folder, adapter)
        graph, = adapter.executor.graphs.values()
        passed = (observed_error == "controlled phase4 failure" and graph.callback_count == 0
                  and summary["status"] == "failed" and not summary["resource_capacity_validated"]
                  if name == "graph_failure" else ends == [7 if name == "resource_delay" else 0]
                  and graph.callback_count == 1 and summary["status"] == "passed")
        passed = passed and all(r["used"] == 0 for r in manager.usage_snapshot().values())
        check = {"name": name, "passed": passed, "stage_end_times_s": ends,
                 "observed_error": observed_error, "callback_count": graph.callback_count}
        write_json(folder / "probe-result.json", check)
        checks.append(check)
    return checks


def hashes(base, files):
    return {p.relative_to(base).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}


def sources():
    files = {p for name in ("schemas/dag/v1", "vidur-alibabacloud/vidur", "scripts/dag_phase4", "tests/dag")
                         for p in (ROOT / name).rglob("*")
                         if p.is_file() and p.suffix in (".py", ".json", ".txt") and "__pycache__" not in p.parts}
    files.add(ROOT / "configs/dag/phase1/data-pairs.csv")
    return hashes(ROOT, files)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    output = (ROOT / args.output).resolve()
    if not output.is_relative_to(ROOT / "results/dag/phase4") or output == ROOT / "results/dag/phase4":
        parser.error("output must be a new directory under results/dag/phase4")
    try:
        output.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        parser.error(str(exc))
    start = time.perf_counter()
    report = {"status": "failed", "checks": [], "accuracy_status": "blocked",
              "hardware_accuracy_claim": False, "profile_nature": "synthetic",
              "accuracy_blocker": "Phase1 data-pairs.csv has no eligible model-reference pairs"}
    manifest = {"command_argv": [sys.executable, str(Path(__file__)), *(sys.argv[1:] if argv is None else argv)]}
    code = 1
    operation_errors = []

    def record_error(exc):
        nonlocal code
        code = 1
        operation_errors.append({"error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()})
        report.update(status="failed", error="; ".join(item["error"] for item in operation_errors))
        write_json(output / "operation-error.json", {
            "error": report["error"], "traceback": "\n".join(item["traceback"] for item in operation_errors),
            "errors": operation_errors})

    try:
        manifest["source_sha256_at_start"] = sources()
        with (ROOT / "configs/dag/phase1/data-pairs.csv").open(encoding="utf-8") as stream:
            eligible = sum(row["status"] == "eligible" for row in csv.DictReader(stream))
        report["eligible_reference_pairs"] = eligible
        if eligible:
            report.update(accuracy_status="not_evaluated", accuracy_blocker="Reference pairs require separate three-way evaluation")
        report["checks"] = run_comparisons(output)
        report["host_probes"] = run_host_probes(output)
        code = 0 if all(item["passed"] for item in report["checks"] + report["host_probes"]) else 1
        report["status"] = "passed" if code == 0 else "failed"
    except Exception as exc:
        record_error(exc)
    try:
        manifest["source_sha256"] = sources()
        manifest["sources_changed_during_run"] = manifest["source_sha256"] != manifest.get("source_sha256_at_start")
        if manifest["sources_changed_during_run"]:
            record_error(RuntimeError("source files changed during acceptance"))
        manifest["dependencies"] = {d.metadata["Name"]: d.version for d in importlib.metadata.distributions()}
        for field, command in (("git_head", ["rev-parse", "HEAD"]), ("git_status", ["status", "--short"]),
                               ("git_diff", ["diff", "--binary"]), ("git_staged_diff", ["diff", "--cached", "--binary"])):
            result = subprocess.run(["git", "-c", f"safe.directory={ROOT.as_posix()}", *command], cwd=ROOT,
                                    capture_output=True, text=True, encoding="utf-8", errors="replace")
            manifest[field] = {"exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
    except Exception as exc:
        record_error(exc)
    report["exit_code"] = code
    write_json(output / "acceptance-report.json", report)
    manifest.update(exit_code=code, python=sys.version, wall_time_s=time.perf_counter() - start)
    try:
        manifest["artifact_sha256"] = hashes(output, {p for p in output.rglob("*") if p.is_file()
                                             and "predictor-cache" not in p.relative_to(output).parts})
    except Exception as exc:
        record_error(exc)
        report["exit_code"] = code
        manifest["exit_code"] = code
        write_json(output / "acceptance-report.json", report)
    write_json(output / "run-manifest.json", manifest)
    print(json.dumps({"status": report["status"], "output": str(output), "exit_code": code}))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
