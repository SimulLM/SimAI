"""Verify phase-3 evidence on both successful and interrupted executions."""
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import uuid

import pytest

from scripts.dag_phase3 import main as acceptance

ROOT = Path(__file__).resolve().parents[2]


def test_phase3_cli_records_failure_probe_dependencies_and_artifact_hashes():
    relative = Path("results/dag/phase3") / ("test-evidence-" + uuid.uuid4().hex)
    command = [sys.executable, "scripts/dag_phase3/main.py", "--output", str(relative)]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert result.returncode == 0, result.stdout + result.stderr
    output = ROOT / relative
    report = json.loads((output / "acceptance-report.json").read_text(encoding="utf-8"))
    manifest = json.loads((output / "run-manifest.json").read_text(encoding="utf-8"))
    assert report["status"] == "passed" and report["exit_code"] == 0
    assert [check["observed_makespan_s"] for check in report["checks"][:3]] == pytest.approx([22e-6, 18e-6, 22e-6])
    failure_check = next(check for check in report["checks"] if check["name"] == "controlled_failure_cleanup")
    assert failure_check["passed"] and all(failure_check["checks"].values())
    with (output / "failure_cleanup/resource_timeline.csv").open(encoding="utf-8", newline="") as stream:
        interval, = list(csv.DictReader(stream))
    assert (float(interval["start_at_s"]), float(interval["end_at_s"])) == (0, 5e-6)
    assert report["kv_lifecycle"]["final_usage"]["used"] == 0
    assert manifest["command_argv"] == [sys.executable, str(ROOT / "scripts/dag_phase3/main.py"), "--output", str(relative)]
    assert manifest["exit_code"] == 0 and not manifest["sources_changed_during_run"]
    assert manifest["dependencies"]["pytest"] and manifest["dependencies"]["jsonschema"]
    for relative_source in ("vidur-alibabacloud/vidur/dag/executor.py",
                            "vidur-alibabacloud/vidur/dag/runtime.py",
                            "schemas/dag/v1/graph.schema.json", "schemas/dag/v1/contracts.py"):
        assert relative_source in manifest["source_sha256"]
    for relative_source, digest in manifest["source_sha256"].items():
        assert hashlib.sha256((ROOT / relative_source).read_bytes()).hexdigest() == digest
    assert "acceptance-report.json" in manifest["artifact_sha256"]
    assert "failure_cleanup/resource_timeline.csv" in manifest["artifact_sha256"]
    assert "shared_compute/input.graph.json" in manifest["artifact_sha256"]
    for relative_artifact, digest in manifest["artifact_sha256"].items():
        assert hashlib.sha256((output / relative_artifact).read_bytes()).hexdigest() == digest
    original = {path.relative_to(output): path.read_bytes() for path in output.rglob("*") if path.is_file()}
    repeated = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert repeated.returncode == 2
    assert original == {path.relative_to(output): path.read_bytes() for path in output.rglob("*") if path.is_file()}


@pytest.mark.parametrize("failure_point", ["scenario", "pytest_process"])
def test_phase3_exception_preserves_failure_report_and_manifest(monkeypatch, tmp_path, failure_point):
    monkeypatch.setattr(acceptance, "output_directory", lambda _: tmp_path)

    def crash(*_):
        raise OSError("injected acceptance failure")

    monkeypatch.setattr(acceptance, "run_scenarios" if failure_point == "scenario" else "run_tests", crash)
    assert acceptance.main(["--output", "unused-test-path"]) == 1
    report = json.loads((tmp_path / "acceptance-report.json").read_text(encoding="utf-8"))
    manifest = json.loads((tmp_path / "run-manifest.json").read_text(encoding="utf-8"))
    error = json.loads((tmp_path / "operation-error.json").read_text(encoding="utf-8"))
    assert report["status"] == "failed" and report["exit_code"] == 1
    assert report["resource_capacity_validated"] is False
    assert "injected acceptance failure" in error["traceback"]
    assert manifest["exit_code"] == 1 and manifest["dependencies"]["jsonschema"]
    assert "operation-error.json" in manifest["artifact_sha256"]
    if failure_point == "pytest_process":
        assert report["checks"] and (tmp_path / "shared_compute/timeline.csv").is_file()


def test_metadata_failure_preserves_reports_and_returns_nonzero(monkeypatch, tmp_path):
    monkeypatch.setattr(acceptance, "output_directory", lambda _: tmp_path)

    def crash():
        raise OSError("injected source hashing failure")

    monkeypatch.setattr(acceptance, "source_hashes", crash)
    monkeypatch.setattr(acceptance, "run_tests", lambda _: {"name": "stub", "passed": True})
    assert acceptance.main(["--output", "unused-test-path"]) == 1
    report = json.loads((tmp_path / "acceptance-report.json").read_text(encoding="utf-8"))
    manifest = json.loads((tmp_path / "run-manifest.json").read_text(encoding="utf-8"))
    error = json.loads((tmp_path / "operation-error.json").read_text(encoding="utf-8"))
    assert report["status"] == "failed" and report["resource_capacity_validated"] is False
    assert "injected source hashing failure" in error["traceback"]
    assert manifest["exit_code"] == 1 and manifest["dependencies"]["jsonschema"]
    assert "operation-error.json" in manifest["artifact_sha256"]
