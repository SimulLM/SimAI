"""Read-only archive audit; --inventory explicitly writes the classified CSV."""
import argparse
import zipfile

from common import ROOT, project_path, read_json, sha256, write_csv, write_json


def audit():
    base = ROOT / "baseline-data"
    manifest = read_json(base / "manifest.json")
    checks, inventory = [], []
    for item in manifest["files"]:
        path = base / item["path"]
        actual = sha256(path) if path.is_file() else None
        checks.append({"path": path.relative_to(ROOT).as_posix(), "expected_sha256": item["sha256"],
                       "actual_sha256": actual, "passed": actual == item["sha256"]})
        name, status = item["path"], item["status"]
        if name.startswith(("communication/analytical/", "communication/ns3/")):
            nature, granularity = "simulated", "collective_or_workload"
        elif name.startswith("moe/loads/"):
            nature, granularity = "synthetic", "expert_or_rank_assignments"
        elif name.startswith("traces/deepseek/derived/"):
            nature, granularity = "derived", "gpu_kernel_category"
        else:
            nature, granularity = "metadata", "not_accuracy_sample"
        metric = "gpu_kernel_duration_or_overlap" if nature == "derived" else ""
        unit = "us" if nature == "derived" else ""
        unit_evidence = "CSV/JSON time field suffixes; fractional timestamp precision still unverified" if nature == "derived" else ""
        if nature == "synthetic":
            metric, unit, unit_evidence = "expert_or_rank_assignments", "assignments", "synthetic load fields; no latency"
        inventory.append({"reference_id": f"archive-{len(inventory)+1:03d}",
            "path": path.relative_to(ROOT).as_posix(), "sha256": item["sha256"],
            "source": item["source"], "nature": nature, "granularity": granularity,
            "metric": metric, "raw_unit": unit, "unit_evidence": unit_evidence, "status": status,
            "eligible_for_accuracy": "false", "identity_missing": "verified_run_identity;metric_and_unit;matching_old_record",
            "purpose": item["purpose"], "reason": item["note"] or "not an independently verified accuracy pair"})
    archive = base / "raw/results.zip"
    expected = manifest["sources"]["results_zip"]["sha256"]
    with zipfile.ZipFile(archive) as zipped:
        files = [i.filename for i in zipped.infolist() if not i.is_dir()]
        raw_traces = [p for p in files if p.endswith(("prefill.json", "decode.json"))]
    return {"files": checks, "file_count": len(checks),
            "hash_failures": [c["path"] for c in checks if not c["passed"]],
            "verified_cost_count": sum(bool(i["eligible_as_verified_cost"]) for i in manifest["files"]),
            "zip_sha256_passed": sha256(archive) == expected,
            "zip_file_count": len(files), "zip_raw_trace_entries": raw_traces}, inventory


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", help="explicitly regenerate inventory CSV")
    args = parser.parse_args()
    report, inventory = audit()
    if args.inventory:
        write_csv(project_path(args.inventory), list(inventory[0]), inventory)
    print(f"files={report['file_count']}, failures={len(report['hash_failures'])}, verified_cost={report['verified_cost_count']}")
    return int(bool(report["hash_failures"]) or not report["zip_sha256_passed"])


if __name__ == "__main__":
    raise SystemExit(main())
