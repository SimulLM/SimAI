import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

import pytest

from vidur.dag.executor import DagExecutor
from vidur.dag.runner import DagRunner, SimulationFailure
from vidur.dag.testing import DependencyOnlyResources
from vidur.dag.trace import snapshot, write_results

ROOT = Path(__file__).resolve().parents[2]


def invoke(command, *args, output=None):
    output = output or Path("results/dag/phase2") / ("test-cli-" + uuid.uuid4().hex)
    result = subprocess.run([sys.executable, "scripts/dag_phase2/main.py", command,
                             "--output", str(output), *args], cwd=ROOT,
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    return result, ROOT / output


def test_cli_generates_actual_timeline_and_complete_manifest():
    result, output = invoke("run", "--graph", "tests/fixtures/dag/v1/serial.graph.json",
                            "--resource-mode", "dependency-only", "--start-time", "2")
    assert result.returncode == 0, result.stderr
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "passed" and summary["resource_mode"] == "dependency_only"
    assert summary["graphs"][0]["makespan_s"] == pytest.approx(10e-6, abs=1e-15)
    assert not summary["resource_capacity_validated"] and not summary["hardware_accuracy_claim"]
    with (output / "timeline.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert [r["task_id"] for r in rows] == ["T1", "T2", "T3", "terminal"]
    assert all(r["completion_count"] == "1" for r in rows)
    manifest = json.loads((output / "run-manifest.json").read_text(encoding="utf-8"))
    assert manifest["exit_code"] == 0 and manifest["dependencies"]["jsonschema"]
    for relative, expected in manifest["input_sha256"].items():
        assert hashlib.sha256((ROOT/relative).read_bytes()).hexdigest() == expected
    assert any("executor.py" in p for p in manifest["code_sha256"])
    assert any("summary.json" in p for p in manifest["artifact_sha256"])


def test_cli_default_refuses_ignored_resource_demands():
    result, output = invoke("run", "--graph", "tests/fixtures/dag/v1/fork_join.graph.json")
    assert result.returncode == 1
    summary = json.loads((output/"summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "failed" and "ResourceManager" in summary["error"]
    assert summary["task_count"] == 0
    manifest = json.loads((output/"run-manifest.json").read_text(encoding="utf-8"))
    assert manifest["exit_code"] == 1


def test_cli_validate_does_not_execute_and_refuses_overwrite():
    result, output = invoke("validate", "--graph", "tests/fixtures/dag/v1/fork_join.graph.json")
    assert result.returncode == 0
    report = json.loads((output/"validation-report.json").read_text(encoding="utf-8"))
    assert report["status"] == "passed" and report["execution_performed"] is False
    assert not (output/"timeline.csv").exists()
    before = {p.name: p.read_bytes() for p in output.iterdir()}
    result, _ = invoke("validate", "--graph", "tests/fixtures/dag/v1/fork_join.graph.json", output=output)
    assert result.returncode == 2
    assert {p.name: p.read_bytes() for p in output.iterdir()} == before


@pytest.mark.parametrize("name", ["negative_duration", "nonfinite", "cycle"])
def test_cli_invalid_input_still_has_failure_evidence(name):
    result, output = invoke("run", "--graph", f"tests/fixtures/dag/v1/invalid/{name}.json")
    assert result.returncode == 1
    assert json.loads((output/"summary.json").read_text(encoding="utf-8"))["status"] == "failed"
    assert json.loads((output/"run-manifest.json").read_text(encoding="utf-8"))["exit_code"] == 1


@pytest.mark.parametrize("value", ["-1", "nan", "inf"])
def test_cli_invalid_time_is_argument_error(value):
    result, output = invoke("run", "--graph", "tests/fixtures/dag/v1/serial.graph.json", "--start-time", value)
    assert result.returncode == 2 and not output.exists()


def test_output_reports_pending_predecessors_and_resource_wait(graph_factory, tmp_path):
    manager = DependencyOnlyResources()
    manager.blocked.add(("synthetic", "A"))
    runner = DagRunner(DagExecutor(manager))
    runner.submit(graph_factory({"A": 1, "B": 1}, (("A", "B"),)))
    with pytest.raises(SimulationFailure):
        runner.run()
    summary = write_results(tmp_path, runner)
    unfinished = {t["task_id"]: t for t in summary["graphs"][0]["unfinished_tasks"]}
    assert unfinished["A"]["resource_wait"] is True
    assert unfinished["B"]["unfinished_predecessors"] == ["A"]
    assert summary["status"] == "failed" and summary["graphs"][0]["makespan_s"] is None


def test_trace_is_deterministic_at_nonzero_submission(graph_factory, tmp_path):
    outputs = []
    for case in range(2):
        output = tmp_path / str(case)
        output.mkdir()
        runner = DagRunner()
        runner.submit(graph_factory({"A": 1, "B": 1}), 5)
        runner.run()
        write_results(output, runner)
        outputs.append([(output/name).read_bytes() for name in ("timeline.csv", "events.csv", "summary.json")])
    assert outputs[0] == outputs[1]


def test_lightweight_import_has_no_inference_dependencies():
    env = dict(os.environ, PYTHONPATH=os.pathsep.join((
        str(ROOT), str(ROOT/"vidur-alibabacloud"), os.environ.get("PYTHONPATH", ""))))
    result = subprocess.run([sys.executable, "-c",
        "from vidur.dag.executor import DagExecutor; import sys; "
        "assert not {'torch','numpy','pandas','vidur.entities','vidur.simulator'} & sys.modules.keys()"],
        cwd=ROOT, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
