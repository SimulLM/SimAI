"""Conservative normalized-record pairing and error calculation."""
import math

from common import ROOT, finite_nonnegative, project_path, read_json, sha256

IDENTITY = ("model", "hardware", "input_sha256", "batch", "tp", "pp", "ep",
            "topology_sha256", "dtype", "metric", "metric_definition")
TIME_SCALE = {"s": 1.0, "ms": 1e-3, "us": 1e-6, "ns": 1e-9}
MISSING = {"", "unknown", "n/a", "na", "none", "null", "pending"}


def known(value):
    return value is not None and str(value).strip().lower() not in MISSING


def normalized_value(record):
    if record["raw_unit"] not in TIME_SCALE:
        raise ValueError("unsupported or unverified time unit")
    factor = finite_nonnegative(record["conversion_to_s"])
    if factor != TIME_SCALE[record["raw_unit"]]:
        raise ValueError("incorrect time conversion")
    return finite_nonnegative(record["raw_value"]) * factor


def validate_record(record):
    for key in (*IDENTITY, "run_id", "version", "group_id", "unit_evidence", "nature"):
        if not known(record.get(key)):
            raise ValueError(f"missing record identity: {key}")
    for key in ("input_sha256", "topology_sha256"):
        value = str(record[key])
        if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise ValueError(f"invalid SHA-256: {key}")
    for key in ("batch", "tp", "pp", "ep"):
        if isinstance(record[key], bool) or not str(record[key]).isdigit() or int(record[key]) < 1:
            raise ValueError(f"invalid positive integer: {key}")
    if record.get("verification") != "verified":
        raise ValueError("record not verified")
    if record["nature"] not in ("measured", "simulated", "estimated"):
        raise ValueError("synthetic/derived/config data cannot be accuracy ground truth")
    evidence = record.get("evidence", [])
    if not evidence:
        raise ValueError("record lacks evidence")
    archive = read_json(ROOT / "baseline-data/manifest.json")
    archive_entries = {"baseline-data/" + item["path"]: item for item in archive["files"]}
    for item in evidence:
        path = project_path(item["path"])
        if "quarantine" in path.parts:
            raise ValueError("quarantine evidence rejected")
        archived = archive_entries.get(item["path"])
        if archived and not archived["eligible_as_verified_cost"]:
            raise ValueError("archive evidence requires independent verification before accuracy use")
        if sha256(path) != item["sha256"]:
            raise ValueError("evidence checksum mismatch")
    normalized_value(record)


def compare_records(reference, old):
    for record in (reference, old):
        validate_record(record)
    if old["nature"] != "simulated":
        raise ValueError("old prediction must be a simulated result")
    for key in IDENTITY:
        if str(reference[key]) != str(old[key]):
            raise ValueError(f"configuration/metric mismatch: {key}")
    if reference["group_id"] != old["group_id"]:
        raise ValueError("pair must share the frozen workload/config group")
    ref_value, old_value = normalized_value(reference), normalized_value(old)
    absolute = abs(old_value - ref_value)
    return {"reference_s": ref_value, "old_s": old_value,
            "absolute_error_s": absolute,
            "relative_error": absolute / abs(ref_value) if ref_value else None,
            "reference_nature": reference["nature"]}


def evaluate_pairs(pairs, split_rows):
    groups = {}
    for row in split_rows:
        if row["split"] not in ("calibration", "validation", "excluded"):
            raise ValueError("invalid dataset split")
        if row["group_id"] in groups:
            raise ValueError("duplicate or leaking group assignment")
        groups[row["group_id"]] = row["split"]
    output, seen, provenance_groups, accepted_records = [], set(), {}, set()
    for pair in pairs:
        if pair["status"] not in ("eligible", "blocked", "excluded"):
            raise ValueError("invalid pair status")
        if pair["group_id"] not in groups:
            raise ValueError("pair group missing from split table")
        if pair["pair_id"] in seen:
            raise ValueError("duplicate pair ID")
        seen.add(pair["pair_id"])
        row = {"pair_id": pair["pair_id"], "group_id": pair["group_id"],
               "reference_record": pair["reference_record"], "old_record": pair["old_record"],
               "status": "excluded", "reason": pair["reason"],
               "reference_s": None, "old_s": None, "absolute_error_s": None,
               "relative_error": None, "reference_nature": None, "metric": None,
               "split": groups.get(pair["group_id"])}
        try:
            if pair["status"] != "eligible":
                raise ValueError(pair["reason"] or "pair is not eligible")
            if row["split"] not in ("calibration", "validation"):
                raise ValueError("pair lacks a frozen calibration/validation split")
            ref = read_json(project_path(pair["reference_record"]))
            old = read_json(project_path(pair["old_record"]))
            if ref["group_id"] != pair["group_id"]:
                raise ValueError("pair group disagrees with record")
            row.update(compare_records(ref, old))
            row.update(status="accepted", reason="", metric=ref["metric"])
            sample_key = (ref["run_id"], old["run_id"], *(str(ref[k]) for k in IDENTITY))
            if sample_key in accepted_records:
                raise ValueError("duplicate sample under another pair ID")
            keys = [("workload", *(str(ref[k]) for k in IDENTITY if k not in ("metric", "metric_definition")))]
            keys += [("reference_evidence", e["sha256"]) for e in ref["evidence"]]
            for key in keys:
                previous = provenance_groups.get(key)
                if previous is not None and previous != pair["group_id"]:
                    raise ValueError("same workload/config or reference evidence assigned to multiple groups")
            for key in keys:
                provenance_groups[key] = pair["group_id"]
            accepted_records.add(sample_key)
        except (ValueError, KeyError, TypeError, OSError) as exc:
            row["status"] = "rejected" if pair["status"] == "eligible" else "excluded"
            row["reason"] = str(exc)
            row.update(reference_s=None, old_s=None, absolute_error_s=None, relative_error=None)
        output.append(row)
    accepted = [row for row in output if row["status"] == "accepted"]
    aggregates = []
    for key in sorted({(r["metric"], r["split"], r["reference_nature"]) for r in accepted}):
        subset = [r for r in accepted if (r["metric"], r["split"], r["reference_nature"]) == key]
        relative = [r["relative_error"] for r in subset if r["relative_error"] is not None]
        aggregates.append({"metric": key[0], "split": key[1], "reference_nature": key[2],
                           "n": len(subset), "relative_n": len(relative),
                           "mae_s": math.fsum(r["absolute_error_s"] for r in subset) / len(subset),
                           "mean_relative_error": math.fsum(relative) / len(relative) if relative else None})
    # Formal E2E acceptance requires both frozen subsets; no pooling across metrics/natures.
    e2e = [r for r in accepted if r["metric"] == "request_e2e"]
    ready = ({r["split"] for r in e2e if r["relative_error"] is not None} == {"calibration", "validation"}
             and not any(r["status"] == "rejected" for r in output))
    return output, {"valid_samples": len(accepted), "excluded_samples": len(output) - len(accepted),
                    "aggregates": aggregates, "primary_metric": "request_e2e_mean_relative_error" if ready else None,
                    "primary_metric_status": "frozen" if ready else "pending",
                    "accuracy_baseline": "passed" if ready else "not_passed",
                    "mean_relative_error": None,
                    "hardware_accuracy_claim": False}
