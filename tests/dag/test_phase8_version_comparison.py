"""Prevent misleading comparisons: exclude fitting data and retain regressions."""
from copy import deepcopy
import json

import pytest

from scripts.dag_phase8.compare_versions import ARCHIVE, Evidence, calculate, load_samples


@pytest.fixture(scope="module")
def archived_samples():
    evidence = Evidence(archive=ARCHIVE)
    try:
        return load_samples(evidence)[0]
    finally:
        evidence.close()


def test_original_archive_recomputes_published_values(archived_samples):
    details, summary = calculate(archived_samples)
    e2e = {r["version"]: r for r in summary if r["metric"] == "E2E"}
    assert len(details) == 27  # 3 validation requests x 3 metrics x 3 versions
    assert e2e["old"]["mean_relative_error_percent"] == pytest.approx(51.03433034012862)
    assert e2e["same_cost"]["mean_relative_error_percent"] == pytest.approx(e2e["old"]["mean_relative_error_percent"])
    assert e2e["revised_cost"]["mean_relative_error_percent"] == pytest.approx(2.483251350535665)
    assert e2e["revised_cost"]["improved"] == 3


def test_calibration_rows_cannot_improve_displayed_score(archived_samples):
    changed = deepcopy(archived_samples)
    changed[0]["revised_cost_s"] = 10000
    assert calculate(changed) == calculate(archived_samples)


def test_regressed_sample_and_positive_bias_are_reported(archived_samples):
    changed = deepcopy(archived_samples)
    changed[1]["revised_cost_s"] = changed[1]["reference_s"] * 3
    details, summary = calculate(changed)
    sample = next(r for r in details if r["sample"] == changed[1]["sample"] and r["metric"] == "E2E" and r["version"] == "revised_cost")
    assert sample["outcome_vs_native"] == "regressed" and sample["signed_bias_ms"] > 0
    assert next(r for r in summary if r["metric"] == "E2E" and r["version"] == "revised_cost")["regressed"] == 1


def test_zero_reference_does_not_create_a_finite_percentage(archived_samples):
    changed = deepcopy(archived_samples)
    changed[1]["reference_s"] = 0
    with pytest.raises(ValueError):
        calculate(changed)


def test_modified_archive_is_rejected_before_reading_results(tmp_path):
    archive = tmp_path / "tampered.zip"
    archive.write_bytes(b"not the original evidence")
    (tmp_path / "SHA256SUMS").write_text("0" * 64 + "  tampered.zip\n")
    with pytest.raises(ValueError, match="archive checksum"):
        Evidence(archive=archive)


def test_local_evidence_matches_archive_and_rejects_tampering(tmp_path, monkeypatch):
    import scripts.dag_phase8.compare_versions as display
    archived = Evidence(archive=ARCHIVE)
    try:
        expected = load_samples(archived)[0]
        local = tmp_path / archived.prefix
        local.mkdir(parents=True)
        (local / "run-manifest.json").write_text(json.dumps(archived.manifest))
        for name, payload in archived.cache.items():
            path = tmp_path / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
    finally:
        archived.close()
    monkeypatch.setattr(display, "ROOT", tmp_path)
    evidence = Evidence(run_dir=local)
    try:
        assert load_samples(evidence)[0] == expected
    finally:
        evidence.close()
    (local / "request-comparison.csv").write_text("modified data")
    evidence = Evidence(run_dir=local)
    try:
        with pytest.raises(ValueError, match="checksum"):
            load_samples(evidence)
    finally:
        evidence.close()


def test_omitting_a_planned_request_is_rejected():
    evidence = Evidence(archive=ARCHIVE)
    try:
        original_read = evidence.read
        def incomplete(relative):
            payload = original_read(relative)
            return b"\n".join(payload.splitlines()[:-1]) if relative == "request-comparison.csv" else payload
        evidence.read = incomplete
        with pytest.raises(ValueError, match="every planned sample"):
            load_samples(evidence)
    finally:
        evidence.close()
