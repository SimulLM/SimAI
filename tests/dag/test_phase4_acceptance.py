import hashlib
import json
from pathlib import Path
import subprocess
import sys
import uuid

import pytest

from scripts.dag_phase4.main import compare

ROOT = Path(__file__).resolve().parents[2]


def test_original_cli_legacy_and_dag_complete_identical_requests():
    relative = Path("results/dag/phase4") / ("test-evidence-" + uuid.uuid4().hex)
    command = [sys.executable, "scripts/dag_phase4/main.py", "--output", str(relative)]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert result.returncode == 0, result.stdout + result.stderr
    output = ROOT / relative
    report = json.loads((output / "acceptance-report.json").read_text(encoding="utf-8"))
    manifest = json.loads((output / "run-manifest.json").read_text(encoding="utf-8"))
    assert report["status"] == "passed" and len(report["checks"]) == 5
    assert all(all(check["checks"].values()) for check in report["checks"])
    assert report["resource_delay_integration"]["passed"]
    assert all(report["resource_delay_integration"]["checks"].values())
    assert report["profile_nature"] == "synthetic" and report["accuracy_status"] == "blocked"
    assert not manifest["sources_changed_during_run"] and manifest["exit_code"] == 0
    for name, digest in manifest["artifact_sha256"].items():
        assert hashlib.sha256((output / name).read_bytes()).hexdigest() == digest
    assert manifest["source_sha256"]["vidur-alibabacloud/vidur/simulator.py"]
    original = (output / "acceptance-report.json").read_bytes()
    repeated = subprocess.run(command, cwd=ROOT, capture_output=True)
    assert repeated.returncode == 2 and (output / "acceptance-report.json").read_bytes() == original


def test_comparison_keeps_counts_exact_and_seconds_tolerant():
    assert compare({"seconds": 0.1}, {"seconds": 0.1 + 1e-14})
    assert not compare({"tokens": 4}, {"tokens": 5})
    assert not compare({"num_processed_tokens": 4.0}, {"num_processed_tokens": 4.0 + 1e-14})
    assert not compare({"completed": True}, {"completed": 1})
    assert not compare([1], [])


def test_acceptance_exception_preserves_evidence(monkeypatch):
    from scripts.dag_phase4 import main as acceptance
    relative = Path("results/dag/phase4") / ("test-failure-" + uuid.uuid4().hex)

    def crash(*_):
        raise OSError("injected CLI launch failure")

    monkeypatch.setattr(acceptance, "run_comparisons", crash)
    assert acceptance.main(["--output", str(relative)]) == 1
    output = ROOT / relative
    report = json.loads((output / "acceptance-report.json").read_text(encoding="utf-8"))
    manifest = json.loads((output / "run-manifest.json").read_text(encoding="utf-8"))
    error = json.loads((output / "operation-error.json").read_text(encoding="utf-8"))
    assert report["status"] == "failed" and manifest["exit_code"] == 1
    assert "injected CLI launch failure" in error["traceback"]
    assert "operation-error.json" in manifest["artifact_sha256"]


@pytest.mark.parametrize("failure_call", [1, 2])
def test_metadata_errors_preserve_failure_report(monkeypatch, failure_call):
    from scripts.dag_phase4 import main as acceptance
    relative = Path("results/dag/phase4") / ("test-metadata-" + uuid.uuid4().hex)
    calls = 0

    def sources():
        nonlocal calls
        calls += 1
        if calls == failure_call:
            raise OSError("injected metadata error")
        return {}

    monkeypatch.setattr(acceptance, "sources", sources)
    monkeypatch.setattr(acceptance, "run_comparisons", lambda _: [])
    monkeypatch.setattr(acceptance, "run_host_probes", lambda _: [])
    assert acceptance.main(["--output", str(relative)]) == 1
    output = ROOT / relative
    report = json.loads((output / "acceptance-report.json").read_text(encoding="utf-8"))
    manifest = json.loads((output / "run-manifest.json").read_text(encoding="utf-8"))
    error = json.loads((output / "operation-error.json").read_text(encoding="utf-8"))
    assert report["status"] == "failed" and manifest["exit_code"] == 1
    assert "injected metadata error" in error["traceback"]
    assert "operation-error.json" in manifest["artifact_sha256"]


def test_dependency_versions_follow_effective_import_order(monkeypatch):
    from types import SimpleNamespace
    from scripts.dag_phase4 import main as acceptance
    relative = Path("results/dag/phase4") / ("test-dependencies-" + uuid.uuid4().hex)
    # Duplicate distributions are yielded in search order; the global copy is last.
    distributions = [SimpleNamespace(metadata={"Name": "numpy"}, version="isolated"),
                     SimpleNamespace(metadata={"Name": "numpy"}, version="global")]
    monkeypatch.setattr(acceptance.importlib.metadata, "distributions", lambda: distributions)
    monkeypatch.setattr(acceptance.importlib.metadata, "version", lambda _: "isolated")
    monkeypatch.setattr(acceptance, "run_comparisons", lambda _: [{"passed": True}])
    monkeypatch.setattr(acceptance, "run_host_probes", lambda _: [{"passed": True}])
    assert acceptance.main(["--output", str(relative)]) == 0
    manifest = json.loads((ROOT / relative / "run-manifest.json").read_text(encoding="utf-8"))
    assert manifest["dependencies"] == {"numpy": "isolated"}
