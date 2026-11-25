"""Audit a FCFS run against immutable pre-fix submission-policy evidence."""
import argparse
from collections import Counter
import csv
from hashlib import sha256
import io
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.dag_phase8.compare_versions import Evidence
from scripts.dag_phase8.mechanism_experiment import error_statistics, save
from scripts.dag_phase4.main import write_csv

TOLERANCE_S = 1e-12


def outcome(before, after):
    difference = before - after
    return "tied" if abs(difference) <= TOLERANCE_S else "improved" if difference > 0 else "regressed"


def samples(evidence):
    rows = list(csv.DictReader(io.StringIO(evidence.read("request-comparison.csv").decode("utf-8"))))
    result = {(row["case"], int(row["request_id"])): row for row in rows}
    if len(result) != len(rows):
        raise ValueError("duplicate requests")
    return result


def audit(evidence):
    """Recheck saved graphs, timings and permit intervals independently of CLI status."""
    graph_count = task_count = 0
    for name in evidence.manifest["artifact_sha256"]:
        if "/dag_expanded/cli/" not in name or not name.endswith("/summary.json"):
            continue
        folder = name.rsplit("/", 1)[0]
        summary = evidence.json(name)
        assert summary["status"] == "passed" and summary["ready_queue_policy"] == "fcfs"
        assert summary["pending_event_count"] == 0 and summary["resource_capacity_validated"]
        assert all(value["used"] == 0 for value in summary["resource_capacity"].values())
        timeline = list(csv.DictReader(io.StringIO(evidence.read(folder+"/timeline.csv").decode())))
        tasks = {(r["graph_id"], r["task_id"]): r for r in timeline}
        assert len(tasks) == len(timeline)
        for row in timeline:
            ready, start, end, duration, wait = [float(row[key]) for key in
                ("ready_at_s", "start_at_s", "end_at_s", "duration_s", "resource_wait_s")]
            assert all(math.isfinite(value) and value >= 0 for value in (ready, start, end, duration, wait))
            assert row["state"] == "COMPLETED" and int(row["completion_count"]) == 1
            assert ready <= start <= end
            assert math.isclose(end-start, duration, abs_tol=TOLERANCE_S)
            assert math.isclose(start-ready, wait, abs_tol=TOLERANCE_S)
        for graph_name in evidence.manifest["artifact_sha256"]:
            if graph_name.startswith(folder+"/graphs/") and graph_name.endswith(".graph.json"):
                graph = evidence.json(graph_name)
                graph_count += 1
                task_count += len(graph["tasks"])
                assert len(graph["tasks"]) == sum(gid == graph["graph_id"] for gid, _ in tasks)
                for source, target in graph["edges"]:
                    assert float(tasks[graph["graph_id"], source]["end_at_s"]) <= float(
                        tasks[graph["graph_id"], target]["start_at_s"])+TOLERANCE_S
        intervals = list(csv.DictReader(io.StringIO(evidence.read(folder+"/resource_timeline.csv").decode())))
        for resource, capacity in summary["resource_capacity"].items():
            events = []
            for row in intervals:
                if row["resource_id"] != resource:
                    continue
                assert row["unit"] == capacity["unit"]
                start, end, amount = float(row["start_at_s"]), float(row["end_at_s"]), int(row["amount"])
                assert start <= end
                if end > start:
                    events.extend(((start, amount), (end, -amount)))
            used = 0
            for _, delta in sorted(events):
                used += delta
                assert 0 <= used <= capacity["capacity"]
            assert used == 0
    if not graph_count:
        raise ValueError("no graphs audited")
    return dict(passed=True, graphs=graph_count, tasks=task_count)


def compare(before, after):
    old_spec, new_spec = before.json("experiment.json"), after.json("experiment.json")
    old_spec.pop("execution_ready_queue_policy", None)
    assert new_spec.pop("execution_ready_queue_policy") == "fcfs"
    assert old_spec == new_spec, "workloads or reference assumptions changed"
    for name in before.manifest["artifact_sha256"]:
        if name.startswith("profiles/") or name == "cost-contract.json":
            assert before.read(name) == after.read(name), "service costs changed: "+name
    for case in old_spec["cases"]:
        folder = "cases/"+case["name"]+"/"
        for name in ("case.json", "requests.csv"):
            assert before.read(folder+name) == after.read(folder+name), "frozen inputs changed"
        # The original seven-case archive predates the secondary-policy header.
        # Normalize only that documented header; every numeric reference field
        # and all other metadata must still be exactly equal.
        original_ref, revised_ref = before.json(folder+"reference.json"), after.json(folder+"reference.json")
        if original_ref["reference_type"] == "independent_decimal_fcfs_queue":
            original_ref["reference_type"] = "independent_decimal_queue"
            original_ref["queue_policy"] = "fcfs"
        assert original_ref == revised_ref, "FCFS reference values changed"
        if folder+"priority-reference.json" in before.manifest["artifact_sha256"]:
            assert before.read(folder+"priority-reference.json") == after.read(folder+"priority-reference.json")
        original, revised = before.json(folder+"resources.json"), after.json(folder+"resources.json")
        assert original.pop("ready_queue_policy", "submission") == "submission"
        assert revised.pop("ready_queue_policy") == "fcfs"
        assert original == revised, "resource topology/capacities changed"
        check = after.json(folder+"checks.json")
        assert check["passed"] and check["functional_passed"], "FCFS timing/functional checks failed"
    old, new = samples(before), samples(after)
    assert old.keys() == new.keys(), "request coverage changed"
    assert len(old) == sum(len(c["tokens"]) for c in old_spec["cases"])
    rows = []
    for key, previous in old.items():
        current = new[key]
        for field in ("role", "prefill_tokens", "arrived_at_s", "reference_e2e_s", "reference_wait_s"):
            assert current[field] == previous[field], "request/reference changed"
        native, old_dag, fixed, reference = [float(value) for value in (
            previous["legacy_e2e_s"], previous["dag_expanded_e2e_s"],
            current["dag_expanded_e2e_s"], current["reference_e2e_s"])]
        assert abs(native-float(current["legacy_e2e_s"])) <= TOLERANCE_S, "native baseline changed"
        values = dict(native=native, submission=old_dag, fcfs=fixed)
        row = dict(case=key[0], request_id=key[1], role=current["role"], reference_e2e_s=reference,
                   vs_previous=outcome(abs(old_dag-reference), abs(fixed-reference)),
                   vs_native=outcome(abs(native-reference), abs(fixed-reference)),
                   prediction_change_s=fixed-old_dag)
        for label, value in values.items():
            row.update({label+"_e2e_s": value, label+"_absolute_error_s": abs(value-reference),
                        label+"_relative_error": abs(value-reference)/reference})
        rows.append(row)
    validation = [r for r in rows if r["role"] == "validation"]
    statistics = {label: error_statistics(validation, label) for label in ("native", "submission", "fcfs")}
    groups = []
    for case in old_spec["cases"]:
        part = [r for r in rows if r["case"] == case["name"]]
        groups.append(dict(case=case["name"], role=case["role"], requests=len(part),
            **{label+"_mean_relative_error": math.fsum(r[label+"_relative_error"] for r in part)/len(part)
               for label in ("native", "submission", "fcfs")},
            **{name:sum(r["vs_previous"] == name for r in part) for name in ("improved", "tied", "regressed")}))
    no_regression = all(r["vs_previous"] != "regressed" and r["vs_native"] != "regressed" for r in rows)
    report = dict(passed=no_regression, tolerance_s=TOLERANCE_S, requests=len(rows),
        validation_requests=len(validation), control_requests=len(rows)-len(validation),
        primary_reference="unchanged independent FCFS simulation", hardware_accuracy_claim=False,
        identical_frozen_inputs_costs_and_native=True, statistics=statistics,
        vs_previous_validation=dict(Counter(r["vs_previous"] for r in validation)),
        vs_native_validation=dict(Counter(r["vs_native"] for r in validation)),
        vs_previous_all=dict(Counter(r["vs_previous"] for r in rows)),
        predictions_shorter=sum(r["prediction_change_s"] < -TOLERANCE_S for r in rows),
        predictions_longer=sum(r["prediction_change_s"] > TOLERANCE_S for r in rows),
        previous_worst_request=max(validation, key=lambda r:r["submission_relative_error"]),
        case_macro_mean_relative_error={label: math.fsum(r[label+"_mean_relative_error"] for r in groups
            if r["role"] == "validation")/sum(r["role"] == "validation" for r in groups)
            for label in ("native", "submission", "fcfs")},
        audit=audit(after), before=before.identity, after=after.identity)
    return rows, groups, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--before-archive", type=Path)
    source.add_argument("--before-run", type=Path)
    parser.add_argument("--after-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    from scripts.dag_finalize.common import result_path
    try:
        output = result_path(output)
    except ValueError as exc:
        parser.error(str(exc))
    before = Evidence(archive=args.before_archive, run_dir=args.before_run)
    after = Evidence(run_dir=args.after_run)
    try:
        rows, groups, report = compare(before, after)
        output.mkdir(parents=True, exist_ok=False)
        write_csv(output/"request-comparison.csv", rows)
        write_csv(output/"case-comparison.csv", groups)
        save(output/"comparison-report.json", report)
        save(output/"manifest.json", dict(command=[sys.executable, *sys.argv],
            source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
            artifact_sha256={p.name:sha256(p.read_bytes()).hexdigest() for p in output.iterdir()}))
        print(json.dumps(report, indent=2))
        return 0 if report["passed"] else 2
    finally:
        before.close()
        after.close()


if __name__ == "__main__":
    raise SystemExit(main())
