"""Evaluate strictly paired normalized records, preserving exclusions."""
import argparse

from common import ROOT, project_path, read_csv, read_json, run_record, write_csv, write_json
from baseline import evaluate_pairs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pairs", required=True)
    parser.add_argument("--split", default="configs/dag/phase1/dataset-split.csv")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    pair_path, split_path = project_path(args.pairs), project_path(args.split)
    pairs = read_csv(pair_path)
    rows, summary = evaluate_pairs(pairs, read_csv(split_path))
    inputs = [pair_path, split_path, ROOT / "baseline-data/manifest.json"]
    for pair in pairs:
        for key in ("reference_record", "old_record"):
            if pair[key]:
                path = project_path(pair[key])
                if path.is_file():
                    inputs.append(path)
                    for evidence in read_json(path).get("evidence", []):
                        source = project_path(evidence["path"])
                        if source.is_file():
                            inputs.append(source)
    inputs.extend((ROOT / "scripts/dag_phase1").glob("*.py"))
    code = 0 if summary["accuracy_baseline"] == "passed" else 2
    output = run_record(args.output, "evaluate", inputs, code, vars(args))
    fields = list(rows[0]) if rows else ["pair_id", "group_id", "reference_record", "old_record", "status", "reason",
                                       "reference_s", "old_s", "absolute_error_s", "relative_error", "reference_nature", "metric", "split"]
    write_csv(output / "old-errors.csv", fields, rows)
    write_json(output / "baseline-summary.json", summary)
    write_json(output / "blockers.json", {
        "accuracy_baseline": summary["accuracy_baseline"],
        "items": [{"pair_id": r["pair_id"], "reason": r["reason"]} for r in rows if r["status"] != "accepted"],
        "requirements": [] if code == 0 else ["recover verified matching reference/old records",
            "freeze independent calibration and validation groups with E2E coverage"]})
    print(f"valid_samples={summary['valid_samples']}; accuracy_baseline={summary['accuracy_baseline']}; output={args.output}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
