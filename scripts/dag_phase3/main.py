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
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vidur-alibabacloud"))

from schemas.dag.v1.contracts import (  # noqa: E402
    CostEstimate, GraphContext, GraphFragment, Placement, ResourceDemand, TaskSpec,
)
from vidur.dag.executor import DagExecutor  # noqa: E402
from vidur.dag.resources import CapacityResourceManager, ResourceCapacity  # noqa: E402
from vidur.dag.runner import DagRunner  # noqa: E402
from vidur.dag.serialization import graph_to_dict  # noqa: E402
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
        fragment = graph_for(name, demands)
        write_json(scenario_output / "input.graph.json", graph_to_dict(fragment))
        write_json(scenario_output / "resource-config.json", {
            key: {"amount": value.amount, "unit": value.unit}
            for key, value in resource_capacities.items()
        })
        runner.submit(fragment)
        observed = runner.run()
        summary = write_results(scenario_output, runner)
        graph = runner.executor.graphs[name]
        tasks = graph.tasks
        invariants = {
            "capacity_intervals_validated": summary["resource_capacity_validated"],
            "every_task_completed_once": all(task.completion_count == 1 for task in tasks.values()),
            "terminal_callback_once": graph.callback_count == 1,
            "every_lease_release_confirmed": all(
                task.release_attempted and task.resource_released_at == task.end_at
                and task.lease is None for task in tasks.values()),
            "final_usage_zero": all(value["used"] == 0 for value in summary["resource_capacity"].values()),
        }
        results.append({
            "name": name, "expected_makespan_s": expected, "observed_makespan_s": observed,
            "passed": abs(observed - expected) <= 1e-15 and all(invariants.values()),
            "invariants": invariants,
            "schedule_s": {task_id: [task.start_at, task.end_at] for task_id, task in tasks.items()},
            "output": f"{name}/", "final_resource_usage": summary["resource_capacity"],
        })
    return results


def run_failure_cleanup(output: Path) -> dict:
    """Archive the controlled 5us failure separately from successful workloads."""
    from vidur.dag.resources import resource_timeline
    from vidur.dag.runner import SimulationFailure
    folder = output / "failure_cleanup"
    folder.mkdir()
    resource_capacities = capacities()
    manager = CapacityResourceManager(resource_capacities)
    executor = DagExecutor(manager, resource_units={key: value.unit for key, value in resource_capacities.items()})
    runner = DagRunner(executor)
    demand = (ResourceDemand("gpu:0", 1, "permits"),)
    fragment = graph_for("failure_cleanup", {task: demand for task in ("T1", "T2", "T3")})
    write_json(folder / "input.graph.json", graph_to_dict(fragment))
    runner.submit(fragment)
    runner.enqueue(executor.fail_task(fragment.graph_id, "T1", 5e-6, "controlled phase3 failure"))
    try:
        runner.run()
    except SimulationFailure:
        pass
    summary = write_results(folder, runner)
    intervals = resource_timeline(executor)
    probe = manager.try_acquire(("external", "probe"), demand)
    wakeups = manager.release(probe, 5e-6)
    checks = {
        "actual_interval_0_to_5us": len(intervals) == 1
            and intervals[0].start_s == 0 and intervals[0].end_s == 5e-6,
        "failed_waiters_removed": not wakeups,
        "final_usage_zero": all(value["used"] == 0 for value in manager.usage_snapshot().values()),
        "failed_run_not_capacity_validated": summary["status"] == "failed"
            and not summary["resource_capacity_validated"],
    }
    return {"name": "controlled_failure_cleanup", "passed": all(checks.values()),
            "expected_workload_status": "failed", "checks": checks, "output": "failure_cleanup/"}


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
    if consumer is not None:
        manager.release(consumer, 4.0)
    result["final_usage"] = manager.usage_snapshot()["kv:0"]
    result["passed"] = (result["consumer_blocked_before_release"]
                        and release_error == "cannot release a pinned KV allocation"
                        and result["consumer_acquired_after_release"]
                        and result["final_usage"]["used"] == 0)
    write_json(output / "kv-lifecycle.json", result)
    return result


def git(*args: str) -> dict:
    result = subprocess.run(["git", "-c", f"safe.directory={ROOT.as_posix()}",
                             "-c", "core.safecrlf=false", *args], cwd=ROOT,
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    return {"exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


def source_hashes() -> dict[str, str]:
    files = set()
    for directory in ("schemas/dag/v1", "vidur-alibabacloud/vidur/dag",
                      "scripts/dag_phase3", "tests/dag", "tests/fixtures/dag/v1"):
        files.update(path for path in (ROOT / directory).rglob("*")
                     if path.is_file() and "__pycache__" not in path.parts)
    files.add(ROOT / "scripts/dag_phase2/requirements.txt")
    return {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(files)}


def run_tests(output: Path) -> dict:
    command = [sys.executable, "-m", "pytest", "tests/dag/test_capacity_resources.py", "-q",
               "--basetemp", str(output / "pytest-tmp"), "--junitxml", str(output / "pytest.xml"),
               "-p", "no:cacheprovider"]
    tests = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    (output / "pytest.log").write_text(tests.stdout + tests.stderr, encoding="utf-8")
    return {"name": "phase3_pytest", "passed": tests.returncode == 0,
            "exit_code": tests.returncode, "command_argv": command}


def artifact_hashes(output: Path) -> dict[str, str]:
    return {path.relative_to(output).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(output.rglob("*")) if path.is_file()
            and "pytest-tmp" not in path.relative_to(output).parts
            and path != output / "run-manifest.json"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="new results/dag/phase3/<run_id> directory")
    args = parser.parse_args(argv)
    try:
        output = output_directory(args.output)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    started = time.perf_counter()
    report = {
        "status": "failed", "error": None,
        "scope": "DAG resource capacity and KV lifecycle correctness",
        "resource_capacity_validated": False, "hardware_accuracy_claim": False,
        "prediction_accuracy_claim": False, "checks": [], "kv_lifecycle": None,
        "limitations": [
            "Task durations and capacities are controlled acceptance inputs, not hardware measurements.",
            "The existing inference execution chain is not connected in phase 3.",
            "No model-reference accuracy comparison is included.",
        ],
    }
    operation_errors = []

    def capture(operation, fallback):
        try:
            return operation()
        except Exception as exc:
            operation_errors.append({"error": f"{type(exc).__name__}: {exc}",
                                     "traceback": traceback.format_exc()})
            return fallback

    initial_sources = capture(source_hashes, {})
    git_start = capture(lambda: {"head": git("rev-parse", "HEAD"),
                                "status": git("status", "--short")}, {})
    code = 1
    try:
        report["checks"] = run_scenarios(output)
        report["checks"].append(run_failure_cleanup(output))
        report["kv_lifecycle"] = run_kv_lifecycle(output)
        report["checks"].append(run_tests(output))
        passed = all(item["passed"] for item in report["checks"]) and report["kv_lifecycle"]["passed"]
        report["status"] = "passed" if passed else "failed"
        report["resource_capacity_validated"] = passed
        code = 0 if passed else 1
    except Exception as exc:
        operation_errors.append({"error": f"{type(exc).__name__}: {exc}",
                                 "traceback": traceback.format_exc()})
    final_sources = capture(source_hashes, {})
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_head": capture(lambda: git("rev-parse", "HEAD"), {}),
        "git_status": capture(lambda: git("status", "--short"), {}),
        "python": sys.version, "python_executable": sys.executable,
        "git_start": git_start,
        "git_diff": capture(lambda: git("diff", "--no-ext-diff", "--binary"), {}),
        "git_staged_diff": capture(lambda: git("diff", "--cached", "--no-ext-diff", "--binary"), {}),
        "command_argv": [sys.executable, str(Path(__file__)), *(sys.argv[1:] if argv is None else argv)],
        "source_sha256": final_sources, "source_sha256_at_start": initial_sources,
        "sources_changed_during_run": final_sources != initial_sources,
        "dependencies": capture(lambda: {distribution.metadata["Name"]: distribution.version
                                         for distribution in importlib.metadata.distributions()}, {}),
        "configuration": vars(args),
    }
    if manifest["sources_changed_during_run"]:
        operation_errors.append({"error": "Source files changed during acceptance", "traceback": ""})

    def save_report():
        nonlocal code
        if operation_errors:
            code = 1
            report["status"] = "failed"
            report["resource_capacity_validated"] = False
            report["error"] = "; ".join(item["error"] for item in operation_errors)
            write_json(output / "operation-error.json", {
                "error": report["error"],
                "traceback": "\n".join(item["traceback"] for item in operation_errors),
                "errors": operation_errors,
            })
        report["exit_code"] = code
        write_json(output / "acceptance-report.json", report)

    save_report()
    manifest["artifact_sha256"] = capture(lambda: artifact_hashes(output), {})
    save_report()
    manifest["exit_code"] = code
    manifest["wall_time_s"] = time.perf_counter() - started
    write_json(output / "run-manifest.json", manifest)
    print(json.dumps({"status": report["status"], "output": str(output), "exit_code": code}, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
