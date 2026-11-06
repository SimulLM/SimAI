"""Run and archive the phase-3 resource-capacity acceptance suite."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vidur-alibabacloud"))

from schemas.dag.v1.contracts import (  # noqa: E402
    CostEstimate, GraphContext, GraphFragment, Placement, ResourceDemand, TaskSpec,
)
from vidur.dag.executor import DagExecutor  # noqa: E402
from vidur.dag.resources import CapacityResourceManager, ResourceCapacity  # noqa: E402
from vidur.dag.runner import DagRunner  # noqa: E402
from vidur.dag.trace import write_json, write_results  # noqa: E402


def output_directory(value: str) -> Path:
    path = (ROOT / value).resolve()
    base = ROOT / "results" / "dag" / "phase3"
    if not path.is_relative_to(base) or path == base:
        raise ValueError("output must be a new directory under results/dag/phase3/<run_id>")
    path.mkdir(parents=True, exist_ok=False)
    return path


def capacities() -> dict[str, ResourceCapacity]:
    return {
        "gpu:0": ResourceCapacity(1, "permits"),
        "nic:0": ResourceCapacity(1, "permits"),
        "kv:0": ResourceCapacity(100, "bytes"),
    }


def cost(duration_s: float, includes: tuple[str, ...]) -> CostEstimate:
    return CostEstimate(duration_s, "phase3_hand_calculated", duration_s * 1e6, "us", 1e-6,
                        "docs/dag/phase1/execution-contract.md", includes)


def graph_for(graph_id: str, demands: dict[str, tuple[ResourceDemand, ...]]) -> GraphFragment:
    context = GraphContext("phase3-batch", 0, "replica0", 0, ("request0",))
    return GraphFragment("1.0", graph_id, context, (
        TaskSpec("T1", "compute", Placement(("gpu:0",)), demands["T1"], cost(10e-6, ("compute",))),
        TaskSpec("T2", "comm", Placement(("gpu:0",), "nic:0"), demands["T2"], cost(4e-6, ("tp",))),
        TaskSpec("T3", "compute", Placement(("gpu:0",)), demands["T3"], cost(8e-6, ("compute",))),
        TaskSpec("terminal", "sync", Placement(), (), cost(0.0, ("sync",))),
    ), (("T1", "T3"), ("T2", "T3"), ("T3", "terminal")), "terminal")


def run_scenarios(output: Path) -> list[dict]:
    scenarios = {
        "shared_compute": ({
            "T1": (ResourceDemand("gpu:0", 1, "permits"),),
            "T2": (ResourceDemand("gpu:0", 1, "permits"),),
            "T3": (ResourceDemand("gpu:0", 1, "permits"),),
        }, 22e-6),
        "independent_compute_nic": ({
            "T1": (ResourceDemand("gpu:0", 1, "permits"),),
            "T2": (ResourceDemand("nic:0", 1, "permits"),),
            "T3": (ResourceDemand("gpu:0", 1, "permits"),),
        }, 18e-6),
        "comm_occupies_compute": ({
            "T1": (ResourceDemand("gpu:0", 1, "permits"),),
            "T2": (ResourceDemand("nic:0", 1, "permits"), ResourceDemand("gpu:0", 1, "permits")),
            "T3": (ResourceDemand("gpu:0", 1, "permits"),),
        }, 22e-6),
    }
    results = []
    for name, (demands, expected) in scenarios.items():
        scenario_output = output / name
        scenario_output.mkdir()
        resource_capacities = capacities()
        units = {resource_id: value.unit for resource_id, value in resource_capacities.items()}
        runner = DagRunner(DagExecutor(CapacityResourceManager(resource_capacities), resource_units=units))
        runner.submit(graph_for(name, demands))
        observed = runner.run()
        summary = write_results(scenario_output, runner)
        tasks = runner.executor.graphs[name].tasks
        results.append({
            "name": name, "expected_makespan_s": expected, "observed_makespan_s": observed,
            "passed": abs(observed - expected) <= 1e-15,
            "schedule_s": {task_id: [task.start_at, task.end_at] for task_id, task in tasks.items()},
            "output": f"{name}/", "final_resource_usage": summary["resource_capacity"],
        })
    return results


def run_kv_lifecycle(output: Path) -> dict:
    manager = CapacityResourceManager(capacities())
    reservation = manager.reserve(("kv", "producer"), "kv:0", 80)
    blocked = manager.reserve(("kv", "consumer"), "kv:0", 30)
    manager.commit(reservation, "request-1")
    pin = manager.pin(("kv", "transfer"), "request-1")
    release_error = None
    try:
        manager.release(reservation, 1.0)
    except RuntimeError as exc:
        release_error = str(exc)
    manager.unpin(pin, 2.0)
    wakeups = manager.release(reservation, 3.0)
    consumer = manager.reserve(("kv", "consumer"), "kv:0", 30)
    result = {
        "capacity_bytes": 100, "producer_reservation_bytes": 80, "consumer_attempt_bytes": 30,
        "consumer_blocked_before_release": blocked is None, "pinned_release_error": release_error,
        "wakeups_after_release": [list(owner) for owner in wakeups],
        "consumer_acquired_after_release": consumer is not None,
        "usage_after_consumer_reservation": manager.usage_snapshot()["kv:0"],
    }
    result["passed"] = (result["consumer_blocked_before_release"]
                        and release_error == "cannot release a pinned KV allocation"
                        and result["consumer_acquired_after_release"])
    write_json(output / "kv-lifecycle.json", result)
    return result


def git(*args: str) -> dict:
    result = subprocess.run(["git", "-c", "core.safecrlf=false", *args], cwd=ROOT,
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    return {"exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


def source_hashes() -> dict[str, str]:
    files = [
        ROOT / "vidur-alibabacloud/vidur/dag/resources.py",
        ROOT / "vidur-alibabacloud/vidur/dag/trace.py",
        ROOT / "tests/dag/test_capacity_resources.py",
        Path(__file__),
    ]
    return {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="new results/dag/phase3/<run_id> directory")
    args = parser.parse_args(argv)
    try:
        output = output_directory(args.output)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    started = time.perf_counter()
    checks = run_scenarios(output)
    kv_lifecycle = run_kv_lifecycle(output)
    command = [sys.executable, "-m", "pytest", "tests/dag/test_capacity_resources.py", "-q",
               "--basetemp", str(output / "pytest-tmp"), "-p", "no:cacheprovider"]
    tests = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    (output / "pytest.log").write_text(tests.stdout + tests.stderr, encoding="utf-8")
    checks.append({"name": "phase3_pytest", "passed": tests.returncode == 0,
                   "exit_code": tests.returncode, "command_argv": command})
    report = {
        "status": "passed" if all(item["passed"] for item in checks) and kv_lifecycle["passed"] else "failed",
        "scope": "DAG resource capacity and KV lifecycle correctness",
        "resource_capacity_validated": True, "hardware_accuracy_claim": False,
        "prediction_accuracy_claim": False, "checks": checks, "kv_lifecycle": kv_lifecycle,
        "limitations": [
            "Task durations and capacities are controlled acceptance inputs, not hardware measurements.",
            "The existing inference execution chain is not connected in phase 3.",
            "No model-reference accuracy comparison is included.",
        ],
    }
    write_json(output / "acceptance-report.json", report)
    write_json(output / "run-manifest.json", {
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "git_head": git("rev-parse", "HEAD"),
        "git_status": git("status", "--short"), "python": sys.version, "python_executable": sys.executable,
        "command_argv": [sys.executable, *sys.argv], "source_sha256": source_hashes(),
        "wall_time_s": time.perf_counter() - started,
    })
    print(json.dumps({"status": report["status"], "output": output.relative_to(ROOT).as_posix()}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
