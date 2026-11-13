"""Compare matched reference, legacy and expanded records using phase-1 admission rules."""
from collections import defaultdict
from math import fsum, isclose
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/dag_phase1"))

from baseline import compare_records, evaluate_pairs
from common import project_path, read_csv, read_json, write_csv, write_json

PHASE1 = ROOT / "configs/dag/phase1"
PHASE5 = ROOT / "configs/dag/phase5"


def updated_rows(inputs, name, key, overlay=None):
    files = (PHASE1 / name, PHASE5 / name)
    if overlay is not None:
        files += (overlay / name,)
    rows = {}
    for path in files:
        inputs.add(path)
        entries = read_csv(path)
        if len({row[key] for row in entries}) != len(entries):
            raise ValueError(f"duplicate {key}: {path}")
        rows.update((row[key], row) for row in entries)
    return list(rows.values())


def evaluate(output, overlay=None):
    inputs = set()
    pairs = updated_rows(inputs, "data-pairs.csv", "pair_id", overlay)
    split = updated_rows(inputs, "dataset-split.csv", "group_id", overlay)
    rows, baseline = evaluate_pairs(pairs, split)
    pairs_by_id = {pair["pair_id"]: pair for pair in pairs}
    aggregates = defaultdict(list)
    for row in rows:
        pair = pairs_by_id[row["pair_id"]]
        row.update(same_cost_s=None, revised_cost_s=None, same_cost_absolute_error_s=None,
                   revised_cost_absolute_error_s=None, same_cost_relative_error=None,
                   revised_cost_relative_error=None, timing_delta_s=None, cost_delta_s=None,
                   error_reduction_s=None, outcome=None, attribution=None, expanded_wall_time_s=None,
                   rerun=pair.get("rerun") or (
                       "Recover matched input/topology/units and reference; import with "
                       "python scripts/dag_phase1/import_results.py --help"
                   ))
        if row["status"] != "accepted":
            continue
        try:
            records = []
            for field in ("reference_record", "old_record", "same_cost_record", "revised_cost_record"):
                path = project_path(pair[field])
                inputs.add(path)
                record = read_json(path)
                inputs.update(project_path(e["path"]) for e in record["evidence"])
                records.append(record)
            reference, _, same_cost, revised = records
            timing = compare_records(reference, same_cost)
            cost = compare_records(reference, revised)
            reduction = row["absolute_error_s"] - cost["absolute_error_s"]
            tied = isclose(row["absolute_error_s"], cost["absolute_error_s"], abs_tol=1e-12)
            attribution = pair.get("attribution")
            if not attribution:
                raise ValueError("missing dependency/overlap/contention/cost attribution")
            wall = revised.get("wall_time_s")
            if wall is not None:
                from common import finite_nonnegative
                wall = finite_nonnegative(wall)
            row.update(
                same_cost_s=timing["old_s"], revised_cost_s=cost["old_s"],
                same_cost_absolute_error_s=timing["absolute_error_s"],
                revised_cost_absolute_error_s=cost["absolute_error_s"],
                same_cost_relative_error=timing["relative_error"], revised_cost_relative_error=cost["relative_error"],
                timing_delta_s=timing["old_s"] - row["old_s"], cost_delta_s=cost["old_s"] - timing["old_s"],
                error_reduction_s=reduction, outcome="tied" if tied else ("improved" if reduction > 0 else "regressed"),
                attribution=attribution, expanded_wall_time_s=wall,
            )
            aggregates[row["metric"], row["split"], row["reference_nature"]].append(row)
        except (KeyError, OSError, ValueError, TypeError) as exc:
            row.update(status="rejected", reason=f"expanded comparison: {exc}")

    summaries = []
    for (metric, split_name, nature), samples in sorted(aggregates.items()):
        relative = [r for r in samples if r["relative_error"] is not None]
        summaries.append(dict(
            metric=metric, split=split_name, reference_nature=nature, samples=len(samples),
            relative_samples=len(relative),
            old_mae_s=fsum(r["absolute_error_s"] for r in samples) / len(samples),
            expanded_mae_s=fsum(r["revised_cost_absolute_error_s"] for r in samples) / len(samples),
            old_mean_relative_error=fsum(r["relative_error"] for r in relative) / len(relative) if relative else None,
            expanded_mean_relative_error=fsum(r["revised_cost_relative_error"] for r in relative) / len(relative)
            if relative else None,
            **{name: sum(r["outcome"] == name for r in samples) for name in ("improved", "tied", "regressed")},
        ))
    blockers = [dict(pair_id=r["pair_id"], reason=r["reason"], rerun=r["rerun"])
                for r in rows if r["status"] != "accepted"]
    validation = [row for row in summaries if row["split"] == "validation"]
    improved = validation and all(
        (row["old_mae_s"] == row["expanded_mae_s"] == 0) or
        (row["old_mae_s"] - row["expanded_mae_s"] > 1e-12 and row["improved"])
        for row in validation
    )
    status = "blocked" if not validation or any(r["status"] == "rejected" for r in rows) else (
        "passed" if improved else "not_improved"
    )
    summary = dict(status=status, scope="phase5_validation_metrics",
                   validation_metrics=sorted({row["metric"] for row in validation}),
                   samples=sum(len(s) for s in aggregates.values()),
                   blocked_samples=len(blockers), primary_metric_status=baseline["primary_metric_status"],
                   hardware_accuracy_claim=False, aggregates=summaries)
    write_csv(output / "accuracy-comparison.csv", list(rows[0]), rows)
    write_json(output / "accuracy-summary.json", summary)
    write_json(output / "blockers.json", blockers)
    return summary, {path for path in inputs if path.is_file()}
