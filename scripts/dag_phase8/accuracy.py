"""Strict three-way validation; historical component evidence is reported separately."""
import csv
from hashlib import sha256
import io
import json
from math import fsum, isclose
from pathlib import Path
import zipfile

from schemas.dag.v1.io import read_json
from scripts.dag_phase4.main import ROOT, write_csv, write_json
from scripts.dag_phase5.accuracy import evaluate as phase5_evaluate
from common import project_path


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def historical_component_evidence(output):
    """Verify the existing delivery package without promoting it to new E2E evidence."""
    archive = ROOT / "docs/dag/phase5/artifacts/20261113-phase5-delivery.zip"
    with zipfile.ZipFile(archive) as outer:
        expected = {line.split()[1]: line.split()[0] for line in outer.read("SHA256SUMS").decode().splitlines() if line.strip()}
        payload = outer.read("20261113-phase5-handoff-01.zip")
        if sha256(payload).hexdigest() != expected["20261113-phase5-handoff-01.zip"]:
            raise ValueError("historical phase-5 archive checksum mismatch")
        with zipfile.ZipFile(io.BytesIO(payload)) as inner:
            prefix = "20261113-phase5-handoff-01/"
            manifest = json.loads(inner.read(prefix + "run-manifest.json"))
            for path, expected_hash in manifest["artifact_sha256"].items():
                if sha256(inner.read(prefix + path)).hexdigest() != expected_hash:
                    raise ValueError(f"historical artifact checksum mismatch: {path}")
            summary = json.loads(inner.read(prefix + "accuracy-summary.json"))
            comparison = list(csv.DictReader(io.StringIO(inner.read(prefix + "accuracy-comparison.csv").decode())))
    result = dict(status="verified_historical_only", archive_sha256=digest(archive),
                  scope="Previous phase-5 TP8 collective simulation, not phase-8 independent request validation",
                  hardware_accuracy_claim=False, summary=summary,
                  samples=[row for row in comparison if row["status"] == "accepted"])
    write_json(output / "historical-component-evidence.json", result)
    return result


def validate_freeze(dataset):
    samples = dataset["samples"]
    if not samples:
        return None
    declaration = dataset.get("parameter_freeze")
    if not isinstance(declaration, dict) or set(declaration) != {"path", "sha256"}:
        raise ValueError("accuracy samples require a hashed parameter_freeze declaration")
    path = project_path(declaration["path"])
    if digest(path) != declaration["sha256"]:
        raise ValueError("parameter freeze checksum mismatch")
    freeze = read_json(path)
    calibration = {s["group_id"] for s in samples if s["split"] == "calibration"}
    validation = {s["group_id"] for s in samples if s["split"] == "validation"}
    if (calibration.intersection(validation) or not calibration or not validation or
            set(freeze.get("calibration_group_ids", [])) != calibration):
        raise ValueError("parameter freeze requires disjoint frozen calibration/validation groups")
    calibration_refs = {digest(project_path(s["reference_record"])) for s in samples if s["split"] == "calibration"}
    if set(freeze.get("calibration_reference_sha256", [])) != calibration_refs:
        raise ValueError("freeze must identify exactly its calibration reference records")
    validation_inputs = {read_json(project_path(s["reference_record"]))["input_sha256"]
                         for s in samples if s["split"] == "validation"}
    if set(freeze.get("validation_input_sha256", [])) != validation_inputs:
        raise ValueError("validation workload identities must be frozen before scoring")
    scopes = freeze.get("scenarios", {})
    if set(scopes) != set(dataset["required_scenarios"]):
        raise ValueError("freeze must declare cost scopes for every required scenario")
    for sample in samples:
        reference = read_json(project_path(sample["reference_record"]))
        frozen = scopes[sample["scenario"]]
        identity = {key: reference[key] for key in ("model", "hardware", "tp", "pp", "ep", "dtype")}
        if frozen.get("scope") != identity:
            raise ValueError("frozen cost scope differs from reference model/hardware/parallelism/dtype")
        frozen_cost = frozen.get("cost_config_sha256")
        if not isinstance(frozen_cost, str) or len(frozen_cost) != 64 or any(c not in "0123456789abcdef" for c in frozen_cost):
            raise ValueError("freeze requires a valid cost configuration hash")
        legacy, same, revised = (read_json(project_path(sample[key])) for key in
                                ("old_record", "same_cost_record", "revised_cost_record"))
        cost_hash = legacy.get("cost_config_sha256")
        if not isinstance(cost_hash, str) or len(cost_hash) != 64 or same.get("cost_config_sha256") != cost_hash:
            raise ValueError("legacy and same-cost predictions must share an explicit cost configuration hash")
        if (revised.get("parameter_freeze_sha256") != declaration["sha256"] or
                revised.get("cost_config_sha256") != frozen_cost):
            raise ValueError("revised prediction does not use the frozen parameters")
    return freeze


def evaluate(output, dataset_path):
    output.mkdir(parents=True, exist_ok=True)
    dataset = read_json(dataset_path)
    if (set(dataset) != {"schema_version", "primary_metric", "reference_nature", "required_scenarios", "parameter_freeze", "samples"}
            or dataset["schema_version"] != "1.0" or dataset["primary_metric"] != "request_e2e"
            or dataset["reference_nature"] not in ("measured", "simulated")
            or not isinstance(dataset["samples"], list) or not isinstance(dataset["required_scenarios"], list)
            or not dataset["required_scenarios"] or len(set(dataset["required_scenarios"])) != len(dataset["required_scenarios"])):
        raise ValueError("invalid frozen phase-8 validation dataset")
    samples = dataset["samples"]
    ids = [s["pair_id"] for s in samples]
    if len(set(ids)) != len(ids) or any(s["scenario"] not in dataset["required_scenarios"] or
            s["split"] not in ("calibration", "validation") for s in samples):
        raise ValueError("duplicate sample ID or unknown scenario/split")
    freeze = validate_freeze(dataset)
    overlay = output / "overlay"
    overlay.mkdir()
    pairs = [dict(pair_id=s["pair_id"], group_id=s["group_id"], reference_record=s["reference_record"],
                  old_record=s["old_record"], same_cost_record=s["same_cost_record"],
                  revised_cost_record=s["revised_cost_record"], status="eligible", reason="",
                  attribution=s["attribution"]) for s in samples]
    splits = {s["group_id"]: s["split"] for s in samples}
    fields = ("pair_id", "group_id", "reference_record", "old_record", "same_cost_record", "revised_cost_record", "status", "reason", "attribution")
    with (overlay / "data-pairs.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(pairs)
    with (overlay / "dataset-split.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=("group_id", "split", "reason"), lineterminator="\n")
        writer.writeheader()
        writer.writerows(dict(group_id=group, split=split, reason="frozen phase-8 dataset") for group, split in splits.items())
    phase5_evaluate(output, overlay)
    with (output / "accuracy-comparison.csv").open(encoding="utf-8", newline="") as stream:
        comparisons = list(csv.DictReader(stream))
    admitted = [row for row in comparisons if row["status"] == "accepted" and row["pair_id"] in ids]
    rejected = [row for row in comparisons if row["status"] == "rejected"]
    primary = [row for row in admitted if row["split"] == "validation" and row["metric"] == dataset["primary_metric"]
               and row["reference_nature"] == dataset["reference_nature"] and row["relative_error"] != ""]
    by_id = {s["pair_id"]: s for s in samples}
    coverage = {by_id[row["pair_id"]]["scenario"] for row in primary}
    missing = sorted(set(dataset["required_scenarios"]) - coverage)
    old = fsum(float(row["relative_error"]) for row in primary) / len(primary) if primary else None
    new = fsum(float(row["revised_cost_relative_error"]) for row in primary) / len(primary) if primary else None
    passed = old is not None and ((old == new == 0) or old - new > 1e-12)
    status = "rejected" if rejected else ("blocked_missing_matched_reference" if missing or not freeze
                                         else ("passed" if passed else "not_improved"))
    report = dict(status=status, primary_metric="request_e2e_mean_relative_error",
        reference_nature=dataset["reference_nature"], primary_metric_status="pending" if missing or not freeze else "frozen",
        validation_samples=len(primary), missing_scenarios=missing, rejected_samples=len(rejected),
        old_mean_relative_error=old, revised_mean_relative_error=new,
        outcomes={outcome: sum(row["outcome"] == outcome for row in primary) for outcome in ("improved", "tied", "regressed")},
        hardware_accuracy_claim=status == "passed" and dataset["reference_nature"] == "measured",
        parameter_freeze_sha256=digest(project_path(dataset["parameter_freeze"]["path"])) if freeze else None,
        blockers="Matched request-level reference, baseline and new predictions are required; synthetic functional runs are excluded.")
    write_json(output / "accuracy-summary.json", report)
    return report
