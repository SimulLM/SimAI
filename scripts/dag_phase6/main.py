"""Original-CLI PD acceptance; absent matched PD references returns exit code 2."""
import argparse
from hashlib import sha256
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "vidur-alibabacloud")]
from scripts.dag_phase4.main import cli_command, run_cli, synthetic_profiles, write_csv, write_json


def pd_command(output, profiles, trace, config, *, tp=1, pp=1):
    command = cli_command("dag_expanded", output, profiles, trace, replicas=2, tp=tp, pp=pp)
    for option in ("--sarathi_scheduler_config_chunk_size", "--sarathi_scheduler_config_batch_size_cap"):
        i = command.index(option)
        del command[i:i+2]
    command[command.index("--replica_scheduler_config_type") + 1] = "split_wise"
    command += ["--global_scheduler_config_type", "split_wise", "--replica_config_pd_node_ratio", "0.5",
                "--split_wise_replica_scheduler_config_batch_size_cap", "4",
                "--dag_pd_config", str(config)]
    return command


def original_cli(output, *, scenarios=None):
    profiles = output / "synthetic-profiles"
    synthetic_profiles(profiles)
    checks = []
    matrix = scenarios or [
        ("single", 1, 1, 134217728, [(0, 8, 4)]),
        ("dual", 1, 1, 134217728, [(0, 8, 4), (0, 8, 4)]),
        ("backpressure", 1, 1, 33554432, [(0, 8, 12), (0, 8, 4)]),
        ("shards", 2, 2, 134217728, [(0, 8, 4), (0, 8, 4)]),
        ("no_decode", 1, 1, 134217728, [(0, 8, 1)]),
    ]
    for name, tp, pp, capacity, requests in matrix:
        folder = output / name
        folder.mkdir()
        trace = folder / "requests.csv"
        write_csv(trace, [dict(arrived_at=t, num_prefill_tokens=p, num_decode_tokens=d) for t,p,d in requests])
        config = folder / "pd-config.json"
        write_json(config, dict(schema_version="1.0", storage_dtype="float16", capacity_bytes_per_shard=capacity,
            bandwidth_bytes_per_s=1e9, latency_s=.001, occupies_gpu=True,
            evidence="Synthetic acceptance parameters; not measured hardware"))
        command = pd_command(folder / "cli", profiles, trace, config, tp=tp, pp=pp)
        summary, result = run_cli(command, folder / "cli")
        pd = json.loads((result/"pd-summary.json").read_text(encoding="utf-8"))
        dag = json.loads((result/"summary.json").read_text(encoding="utf-8"))
        migrations = pd["migrations"]
        invariants = dict(
            all_requests_completed=summary["status"] == "completed" and len(summary["requests"]) == len(requests)
                and all(r["completed"] and r["num_processed_tokens"] == p+d for r,(_,p,d) in zip(summary["requests"], requests)),
            kv_ready_gate=all(m["first_decode_start_s"] is None or m["first_decode_start_s"] >= m["kv_ready_at_s"] for m in migrations),
            kv_cleanup=not pd["cleanup_errors"] and all(m["state"]=="COMPLETED" and not m["source_reservations"]
                and not m["destination_reservations"] and not m["pins"] for m in migrations),
            capacities=dag["resource_capacity_validated"] and all(v["used"]==0 for v in pd["resource_capacity"].values()),
            terminal_once=all(g["terminal_callback_count"]==1 for g in dag["graphs"]),
            stage_end_once=all(s["completion_count"]==1 for s in summary["stages"]),
            queue_drained=dag["pending_event_count"]==0,
        )
        if name == "backpressure":
            invariants["capacity_wait_observed"] = any(m["destination_reserved_at_s"] > m["prefill_completed_at_s"]
                for m in migrations if m["graph_id"])
        if name == "no_decode":
            invariants["no_useless_transfer"] = all(m["graph_id"] is None for m in migrations)
        checks.append(dict(name=name, passed=all(invariants.values()), checks=invariants))
        write_json(folder/"checks.json", checks[-1])
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--skip-tests", action="store_true", help="development CLI probes only; not full acceptance")
    args = parser.parse_args()
    os.environ["PYTHONPATH"] = os.pathsep.join((str(ROOT / "vidur-alibabacloud"), str(ROOT), os.environ.get("PYTHONPATH", "")))
    os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    os.environ["WANDB_MODE"] = "disabled"
    output = (ROOT/args.output).resolve()
    if not output.is_relative_to(ROOT/"results/dag/phase6") or output == ROOT/"results/dag/phase6":
        parser.error("output must be a new results/dag/phase6/<run_id>")
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    checks, error, code = [], None, 1
    try:
        checks = original_cli(output)
        if not args.skip_tests:
            command = [sys.executable, "-m", "pytest", "tests/test_dag_phase1_contracts.py", "tests/dag", "-q",
                       "--basetemp", str(output/"pytest-tmp"), "--junitxml", str(output/"pytest.xml")]
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
            (output/"pytest.log").write_text(result.stdout+result.stderr, encoding="utf-8")
            checks.append(dict(name="full_regression", passed=result.returncode==0, command=command, exit_code=result.returncode))
        code = 2 if all(c["passed"] for c in checks) else 1
    except Exception:
        error = traceback.format_exc()
        (output/"operation-error.txt").write_text(error, encoding="utf-8")
        print(error, file=sys.stderr)
    write_json(output/"acceptance-report.json", dict(functional_status="passed" if code==2 else "failed",
        accuracy_status="blocked_missing_matched_pd_reference", checks=checks, error=error,
        full_regression_run=not args.skip_tests, hardware_accuracy_claim=False, exit_code=code))
    def git(*argv):
        return subprocess.run(["git", *argv],cwd=ROOT,capture_output=True,text=True,encoding="utf-8",errors="replace").stdout
    sources = [p for directory in ("vidur-alibabacloud/vidur", "schemas/dag", "scripts", "tests/dag", "docs/dag/phase6")
               for p in (ROOT/directory).rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    def hashes(paths):
        return {p.relative_to(ROOT).as_posix():sha256(p.read_bytes()).hexdigest() for p in paths}
    write_json(output/"run-manifest.json", dict(command=[sys.executable,*sys.argv], python=sys.version,
        git_head=git("rev-parse","HEAD"), git_status=git("status","--short"), git_diff=git("diff","--binary"),
        dependencies={d.metadata["Name"]: d.version for d in importlib.metadata.distributions()},
        source_sha256=hashes(sources), artifact_sha256=hashes([p for p in output.rglob("*")
            if p.is_file() and "pytest-tmp" not in p.parts and "predictor-cache" not in p.parts]),
        exit_code=code, wall_time_s=time.perf_counter()-started, seed=42, profile_nature="synthetic"))
    print(f"functional={'passed' if code==2 else 'failed'}; accuracy=blocked; output={output}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
