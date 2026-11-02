"""Repository-local CLI for static validation, execution and phase-2 acceptance."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vidur-alibabacloud"))

from schemas.dag.v1.io import finite_nonnegative, read_json
from vidur.dag.executor import DagExecutor
from vidur.dag.runner import DagRunner
from vidur.dag.serialization import load_graph
from vidur.dag.trace import write_json, write_results


def cli_time(value):
    try:
        return finite_nonnegative(float(value))
    except (ValueError, OverflowError) as exc:
        raise argparse.ArgumentTypeError("time must be finite and nonnegative") from exc


def project_file(value):
    path = Path(value)
    path = (ROOT / path).resolve() if not path.is_absolute() else path.resolve()
    if not path.is_relative_to(ROOT) or not path.is_file():
        raise ValueError(f"input must be an existing file within the repository: {value}")
    return path


def new_output(value):
    path = (ROOT / value).resolve()
    base = ROOT / "results/dag/phase2"
    if not path.is_relative_to(base) or path == base:
        raise ValueError("output must be a new directory under results/dag/phase2/<run_id>")
    path.mkdir(parents=True, exist_ok=False)
    return path


def git(*args):
    result = subprocess.run(["git", "-c", "core.safecrlf=false", *args], cwd=ROOT,
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    return dict(exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr)


def manifest(output, args, inputs, code, elapsed):
    sources = []
    for directory in ("schemas/dag/v1", "vidur-alibabacloud/vidur/dag", "scripts/dag_phase2",
                      "scripts/dag_phase1", "tests/dag", "tests/fixtures/dag/v1", "configs/dag/phase1"):
        sources.extend(p for p in (ROOT / directory).rglob("*")
                       if p.is_file() and "__pycache__" not in p.parts)
    sources += [ROOT / "tests/test_dag_phase1_contracts.py", ROOT / ".gitattributes"]
    def hashes(paths):
        return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(set(paths))}
    artifacts = [p for p in output.rglob("*") if p.is_file() and "pytest-tmp" not in p.parts]
    write_json(output / "run-manifest.json", dict(
        schema_version="1.0", operation=args.command, created_at_utc=datetime.now(timezone.utc).isoformat(),
        command_argv=[sys.executable, *sys.argv], cwd=str(ROOT),
        git_head=git("rev-parse", "HEAD"), git_status=git("status", "--short"),
        git_diff=git("diff", "--no-ext-diff", "--binary"),
        python=sys.version, python_executable=sys.executable,
        dependencies={d.metadata["Name"]: d.version for d in importlib.metadata.distributions()},
        input_sha256=hashes(inputs), code_sha256=hashes(sources), artifact_sha256=hashes(artifacts),
        configuration=vars(args), exit_code=code, wall_time_s=elapsed,
        seed=20261102 if args.command == "acceptance" else None,
        seed_reason="fixed random DAG test seed" if args.command == "acceptance" else "no random generator",
    ))


def execute(args, output, inputs):
    runner = DagRunner(DagExecutor(dependency_only=args.resource_mode == "dependency-only"))
    error = None
    try:
        graph_path = project_file(args.graph)
        inputs.append(graph_path)
        graph = load_graph(graph_path)
        runner.submit(graph, args.start_time)
        runner.run()
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    summary = write_results(output, runner, error=error)
    print(f"status={summary['status']}; resource_mode={summary['resource_mode']}; output={output.relative_to(ROOT).as_posix()}")
    if error:
        print(error, file=sys.stderr)
    return 0 if summary["status"] == "passed" else 1


def validate(args, output, inputs):
    try:
        path = project_file(args.graph)
        inputs.append(path)
        graph = load_graph(path)
        report = dict(status="passed", graph_id=graph.graph_id, task_count=len(graph.tasks),
                      execution_performed=False, resource_capacity_validated=False)
        code = 0
    except Exception as exc:
        report = dict(status="failed", error=f"{type(exc).__name__}: {exc}", execution_performed=False)
        code = 1
    write_json(output / "validation-report.json", report)
    print(f"status={report['status']}; execution_performed=false")
    return code


def acceptance(args, output, inputs):
    import math
    checks = []
    for name in ("serial", "fork_join", "resource_contention"):
        folder = output / name
        folder.mkdir()
        runner = DagRunner(DagExecutor(dependency_only=True))
        error = None
        try:
            source = ROOT / f"tests/fixtures/dag/v1/{name}.graph.json"
            expected_path = source.with_name(f"{name}.expected.json")
            inputs.extend((source, expected_path))
            runner.submit(load_graph(source))
            runner.run()
            # Expectations are consumed only after scheduling is finished.
            scenarios = read_json(expected_path)["scenarios"]
            expected = next((s for s in scenarios if s.get("name") == "independent"), scenarios[0])
            graph = runner.executor.graphs[name]
            for tid, interval in expected["schedule_s"].items():
                task = graph.tasks[tid]
                if not all(math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-15)
                           for a, b in zip((task.start_at, task.end_at), interval)):
                    raise AssertionError(f"unexpected timing: {tid}")
                if task.completion_count != 1:
                    raise AssertionError(f"unexpected completion count: {tid}")
            if graph.callback_count != 1:
                raise AssertionError("terminal callback count differs from one")
            if not math.isclose(graph.finished_at, expected["makespan_s"], rel_tol=1e-12, abs_tol=1e-15):
                raise AssertionError("unexpected makespan")
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        result = write_results(folder, runner, error=error)
        checks.append(dict(name=name, passed=result["status"] == "passed", error=error,
                           resource_mode="dependency_only", resource_capacity_validated=False,
                           makespan_s=result["graphs"][0]["makespan_s"] if result["graphs"] else None))
    command = [sys.executable, "-m", "pytest", "tests/test_dag_phase1_contracts.py", "tests/dag", "-q",
               "--basetemp", str(output / "pytest-tmp"), "--junitxml", str(output / "pytest.xml")]
    tests = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    (output / "pytest.log").write_text(tests.stdout + tests.stderr, encoding="utf-8")
    print(tests.stdout)
    checks.append(dict(name="phase1_and_phase2_tests", passed=tests.returncode == 0,
                       exit_code=tests.returncode, command_argv=command))
    passed = all(check["passed"] for check in checks)
    write_json(output / "acceptance-report.json", dict(
        status="passed" if passed else "failed", checks=checks,
        scope="DAG execution correctness", resource_capacity_validated=False,
        accuracy_baseline="pending", hardware_accuracy_claim=False,
        deferred=["capacity enforcement and KV", "inference integration", "prediction accuracy improvement"],
    ))
    print(f"acceptance={'passed' if passed else 'failed'}; output={output.relative_to(ROOT).as_posix()}")
    return 0 if passed else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "run", "acceptance"):
        sub = commands.add_parser(name)
        sub.add_argument("--output", required=True, help="new results/dag/phase2/<run_id> directory")
        if name != "acceptance":
            sub.add_argument("--graph", required=True)
        if name == "run":
            sub.add_argument("--resource-mode", choices=("resource-free", "dependency-only"), default="resource-free")
            sub.add_argument("--start-time", type=cli_time, default=0.0)
    args = parser.parse_args(argv)
    try:
        output = new_output(args.output)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    inputs, started = [], time.perf_counter()
    try:
        code = {"run": execute, "validate": validate, "acceptance": acceptance}[args.command](args, output, inputs)
    except Exception as exc:
        write_json(output / "operation-error.json", dict(error=f"{type(exc).__name__}: {exc}"))
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        code = 1
    manifest(output, args, inputs, code, time.perf_counter()-started)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
