"""Contract and audit tests; no execution-core behavior is implied."""
import copy
import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/dag_phase1"))
from common import read_json, sha256
import baseline
from baseline import compare_records, evaluate_pairs
from graph_validation import validate_graph, validate_expectation
from probe_aicb import probe

FIXTURES = ROOT / "tests/fixtures/dag/v1"


@pytest.mark.parametrize("name", ["serial", "fork_join", "resource_contention"])
def test_hand_calculated_schedules(name):
    validate_expectation(read_json(FIXTURES / f"{name}.graph.json"),
                         read_json(FIXTURES / f"{name}.expected.json"))


@pytest.mark.parametrize("path", sorted((FIXTURES / "invalid").glob("*.json")), ids=lambda p: p.stem)
def test_reject_invalid_graph(path):
    from jsonschema import ValidationError
    with pytest.raises((ValueError, ValidationError)):
        validate_graph(read_json(path))


def test_zero_duration_chain_and_serialization():
    graph = read_json(FIXTURES / "serial.graph.json")
    for task in graph["tasks"]:
        task["cost"]["raw_value"] = task["cost"]["duration_s"] = 0
    order = validate_graph(graph)
    assert order == ["T1", "T2", "T3", "terminal"]
    assert validate_graph(json.loads(json.dumps(graph))) == order


def test_reject_early_join_and_resource_overcommit():
    graph = read_json(FIXTURES / "resource_contention.graph.json")
    expected = read_json(FIXTURES / "resource_contention.expected.json")
    expected["scenarios"][0]["schedule_s"]["T2"] = [0, 4e-6]
    with pytest.raises(ValueError, match="overcommit"):
        validate_expectation(graph, expected)
    expected = read_json(FIXTURES / "resource_contention.expected.json")
    expected["scenarios"][0]["schedule_s"]["T3"] = [0, 8e-6]
    with pytest.raises(ValueError, match="dependency"):
        validate_expectation(graph, expected)


@pytest.fixture
def records(tmp_path, monkeypatch):
    (tmp_path / "baseline-data").mkdir()
    (tmp_path / "baseline-data/manifest.json").write_text('{"files": []}', encoding="utf-8")
    source = tmp_path / "measurement.csv"
    source.write_text("value\n10\n", encoding="utf-8")
    monkeypatch.setattr(baseline, "ROOT", tmp_path)
    monkeypatch.setattr(baseline, "project_path", lambda p: tmp_path / p)
    reference = dict(model="fixture-model", hardware="fixture-gpu", input_sha256="a" * 64,
                     batch=1, tp=1, pp=1, ep=1, topology_sha256="b" * 64, dtype="fp16",
                     metric="request_e2e", metric_definition="completion_minus_arrival",
                     run_id="reference-run", version="fixture-version", group_id="group-a",
                     unit_evidence="fixture CSV milliseconds", nature="measured", verification="verified",
                     raw_value=10, raw_unit="ms", conversion_to_s=0.001,
                     evidence=[dict(path="measurement.csv", sha256=sha256(source))])
    old = copy.deepcopy(reference)
    old.update(raw_value=12, nature="simulated", run_id="old-run")
    return reference, old, tmp_path


def test_independent_known_error(records):
    ref, old, _ = records
    result = compare_records(ref, old)
    assert result["reference_s"] == pytest.approx(0.01)
    assert result["absolute_error_s"] == pytest.approx(0.002)
    assert result["relative_error"] == pytest.approx(0.2)


def test_zero_reference_only_absolute(records):
    ref, old, _ = records
    ref["raw_value"] = 0
    result = compare_records(ref, old)
    assert result["relative_error"] is None
    assert result["absolute_error_s"] == pytest.approx(0.012)


@pytest.mark.parametrize("change", ["mismatch", "unknown", "wrong_unit", "nan", "quarantine", "checksum", "synthetic", "unverified"])
def test_bad_baseline_records(records, change):
    ref, old, _ = records
    if change == "mismatch": old["tp"] = 2
    elif change == "unknown": ref["hardware"] = old["hardware"] = "unknown"
    elif change == "wrong_unit": old["raw_unit"] = "ticks"
    elif change == "nan": old["raw_value"] = float("nan")
    elif change == "quarantine": ref["evidence"][0]["path"] = "baseline-data/quarantine/failure.csv"
    elif change == "checksum": ref["evidence"][0]["sha256"] = "0" * 64
    elif change == "synthetic": ref["nature"] = "synthetic"
    elif change == "unverified": ref["verification"] = "unverified"
    with pytest.raises(ValueError):
        compare_records(ref, old)


def test_archive_status_cannot_be_promoted_by_record(records):
    ref, old, root = records
    source = root / "baseline-data/historical.csv"
    source.write_text("historical", encoding="utf-8")
    (root / "baseline-data/manifest.json").write_text(json.dumps({"files": [
        {"path": "historical.csv", "eligible_as_verified_cost": False}]}), encoding="utf-8")
    ref["evidence"] = [dict(path="baseline-data/historical.csv", sha256=sha256(source))]
    with pytest.raises(ValueError, match="independent verification"):
        compare_records(ref, old)


def test_group_split_and_aggregation(records):
    ref, old, root = records
    pairs, splits = [], []
    for group, split in [("group-a", "calibration"), ("group-b", "validation")]:
        ref, old = copy.deepcopy(ref), copy.deepcopy(old)
        ref["group_id"] = old["group_id"] = group
        if group == "group-b":
            ref["input_sha256"] = old["input_sha256"] = "c" * 64
            evidence = root / "measurement-b.csv"
            evidence.write_text("value\n20\n", encoding="utf-8")
            ref["evidence"] = old["evidence"] = [dict(path="measurement-b.csv", sha256=sha256(evidence))]
        for prefix, record in [("ref", ref), ("old", old)]:
            (root / f"{prefix}-{group}.json").write_text(json.dumps(record), encoding="utf-8")
        pairs.append(dict(pair_id=group, group_id=group, status="eligible", reason="",
                          reference_record=f"ref-{group}.json", old_record=f"old-{group}.json"))
        splits.append(dict(group_id=group, split=split))
    rows, summary = evaluate_pairs(pairs, splits)
    assert len(rows) == summary["valid_samples"] == 2
    assert summary["accuracy_baseline"] == "passed"
    assert summary["aggregates"][0]["mean_relative_error"] == pytest.approx(0.2)
    with pytest.raises(ValueError, match="leaking"):
        evaluate_pairs(pairs, splits + [dict(group_id="group-a", split="validation")])


def test_no_data_is_not_zero_error():
    rows, summary = evaluate_pairs([], [])
    assert rows == []
    assert summary["valid_samples"] == 0
    assert summary["mean_relative_error"] is None
    assert summary["primary_metric"] is None
    assert summary["accuracy_baseline"] == "not_passed"


def test_evidence_cannot_leak_between_groups(records):
    ref, old, root = records
    pairs = []
    for group in ("group-a", "group-b"):
        for prefix, record in (("ref", ref), ("old", old)):
            record = dict(record, group_id=group)
            (root / f"{prefix}-{group}.json").write_text(json.dumps(record), encoding="utf-8")
        pairs.append(dict(pair_id=group, group_id=group, status="eligible", reason="",
                          reference_record=f"ref-{group}.json", old_record=f"old-{group}.json"))
    rows, summary = evaluate_pairs(pairs, [dict(group_id="group-a", split="calibration"),
                                         dict(group_id="group-b", split="validation")])
    assert rows[1]["status"] == "rejected"
    assert summary["accuracy_baseline"] == "not_passed"


def test_import_cli_keeps_source_and_refuses_overwrite():
    import subprocess
    import uuid
    target = Path("results/dag/phase1") / ("test-import-" + uuid.uuid4().hex) / "old-record.json"
    folder = ROOT / target.parent
    folder.mkdir(parents=True)
    source = folder / "old.csv"
    source.write_text("latency_ms\n12\n", encoding="utf-8")
    metadata = folder / "metadata.json"
    metadata.write_text(json.dumps(dict(raw_unit="ms", conversion_to_s=0.001)), encoding="utf-8")
    command = [sys.executable, "scripts/dag_phase1/import_results.py", "--csv", source.relative_to(ROOT).as_posix(),
               "--row", "0", "--column", "latency_ms", "--metadata", metadata.relative_to(ROOT).as_posix(),
               "--output", target.as_posix()]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    record = read_json(ROOT / target)
    assert record["raw_value"] == 12
    assert record["verification"] == "unverified"
    assert record["evidence"][0]["sha256"] == sha256(source)
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    assert result.returncode != 0
    assert "refusing to overwrite" in result.stderr


def test_contracts_import_without_vidur():
    spec = importlib.util.spec_from_file_location("phase1_contracts", ROOT / "schemas/dag/v1/contracts.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    assert module.TaskState.READY.value == "READY"
    assert module.GraphAppend.__annotations__["graph_id"] == "str"


def test_controlled_probe_reproduces_unit_defect():
    result = probe()
    assert result["layer_duration_s"] == pytest.approx(0.003)
    assert result["stage_duration_s"] == pytest.approx(0.000003)
