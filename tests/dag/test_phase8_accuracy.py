"""Admission rejects leakage, scope mismatch, tampering and synthetic ground truth."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

import pytest

from scripts.dag_phase4.main import ROOT, write_json
from scripts.dag_phase8.accuracy import evaluate, validate_freeze


def fixture_dataset(tmp_path, *, revised=1.1):
    samples = []
    refs = []
    for split in ("calibration", "validation"):
        evidence = tmp_path / f"{split}.txt"
        evidence.write_text(f"simulated unit test {split}")
        record = dict(model="unit", hardware="unit", input_sha256=sha256(split.encode()).hexdigest(),
            topology_sha256="a" * 64, batch=1, tp=1, pp=1, ep=1, dtype="fp16", metric="request_e2e",
            metric_definition="unit fixture E2E seconds", run_id=split, version="unit-test", group_id=split,
            nature="simulated", verification="verified", raw_value=1, raw_unit="s", conversion_to_s=1,
            unit_evidence="unit test only; not production accuracy evidence",
            evidence=[dict(path=evidence.relative_to(ROOT).as_posix(), sha256=sha256(evidence.read_bytes()).hexdigest())])
        ref = tmp_path / f"{split}-reference.json"
        write_json(ref, record)
        refs.append(ref)
        sample = dict(pair_id="unit_" + split, group_id=split, split=split, scenario="joint", attribution="unit cost test",
                      reference_record=ref.relative_to(ROOT).as_posix())
        for role, value in (("old", 1.5), ("same_cost", 1.5), ("revised_cost", revised)):
            path = tmp_path / f"{split}-{role}.json"
            write_json(path, dict(record, raw_value=value, cost_config_sha256="b" * 64))
            sample[role + "_record"] = path.relative_to(ROOT).as_posix()
        samples.append(sample)
    freeze = tmp_path / "freeze.json"
    write_json(freeze, dict(calibration_group_ids=["calibration"],
        calibration_reference_sha256=[sha256(refs[0].read_bytes()).hexdigest()],
        validation_input_sha256=[json.loads(refs[1].read_text())["input_sha256"]],
        scenarios=dict(joint=dict(scope={key: record[key] for key in ("model", "hardware", "tp", "pp", "ep", "dtype")},
                                  cost_config_sha256="b" * 64))))
    frozen_hash = sha256(freeze.read_bytes()).hexdigest()
    for sample in samples:
        path = ROOT / sample["revised_cost_record"]
        write_json(path, dict(json.loads(path.read_text()), parameter_freeze_sha256=frozen_hash))
    dataset = dict(schema_version="1.0", primary_metric="request_e2e", reference_nature="simulated",
                   required_scenarios=["joint"], parameter_freeze=dict(path=freeze.relative_to(ROOT).as_posix(), sha256=frozen_hash),
                   samples=samples)
    path = tmp_path / "dataset.json"
    write_json(path, dataset)
    return path, dataset


def test_empty_dataset_remains_blocked(tmp_path):
    report = evaluate(tmp_path / "out", ROOT / "configs/dag/phase8/validation.json")
    assert report["validation_samples"] == 0 and report["primary_metric_status"] == "pending"
    assert report["status"] == "blocked_missing_matched_reference"
    assert not report["hardware_accuracy_claim"]


def test_verified_simulation_reference_can_score_without_hardware_claim(tmp_path):
    path, _ = fixture_dataset(tmp_path)
    report = evaluate(tmp_path / "out", path)
    assert report["status"] == "passed" and report["validation_samples"] == 1
    assert report["old_mean_relative_error"] == .5
    assert report["revised_mean_relative_error"] == pytest.approx(.1)
    assert not report["hardware_accuracy_claim"]


def test_regression_report_does_not_claim_improvement(tmp_path):
    path, _ = fixture_dataset(tmp_path, revised=2)
    report = evaluate(tmp_path / "out", path)
    assert report["status"] == "not_improved" and report["outcomes"]["regressed"] == 1


@pytest.mark.parametrize("mutation", ["leak", "hash", "scope", "cost"])
def test_freeze_or_cost_identity_cannot_be_changed(tmp_path, mutation):
    _, data = fixture_dataset(tmp_path)
    if mutation == "leak":
        data["samples"][1]["group_id"] = "calibration"
    elif mutation == "hash":
        data["parameter_freeze"]["sha256"] = "0" * 64
    else:
        freeze_path = ROOT / data["parameter_freeze"]["path"]
        freeze = json.loads(freeze_path.read_text())
        if mutation == "scope":
            freeze["scenarios"]["joint"]["scope"]["hardware"] = "other"
        else:
            freeze["scenarios"]["joint"]["cost_config_sha256"] = "c" * 64
        write_json(freeze_path, freeze)
        data["parameter_freeze"]["sha256"] = sha256(freeze_path.read_bytes()).hexdigest()
    with pytest.raises(ValueError):
        validate_freeze(data)


def test_synthetic_reference_rejected_even_with_valid_hashes(tmp_path):
    path, data = fixture_dataset(tmp_path)
    reference = ROOT / data["samples"][1]["reference_record"]
    write_json(reference, dict(json.loads(reference.read_text()), nature="synthetic"))
    report = evaluate(tmp_path / "out", path)
    assert report["status"] == "rejected" and not report["hardware_accuracy_claim"]


def test_identical_reference_evidence_cannot_leak_between_splits(tmp_path):
    path, data = fixture_dataset(tmp_path)
    first = json.loads((ROOT / data["samples"][0]["reference_record"]).read_text())
    second_path = ROOT / data["samples"][1]["reference_record"]
    write_json(second_path, dict(json.loads(second_path.read_text()), evidence=first["evidence"]))
    report = evaluate(tmp_path / "out", path)
    assert report["status"] == "rejected"
