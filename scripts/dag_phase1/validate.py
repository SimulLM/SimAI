"""Phase-1 static acceptance, provenance, archive checks and controlled cost probe."""
import argparse
import ast

from common import ROOT, project_path, read_csv, read_json, run_record, write_json
from audit_archive import audit
from baseline import evaluate_pairs
from graph_validation import validate_graph, validate_expectation
from jsonschema import ValidationError
from probe_aicb import probe


def source_audit():
    path = ROOT / "vidur-alibabacloud/vidur/scheduler/global_scheduler/splitwise_global_scheduler.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    calls = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute) and n.func.attr == "add_kv_cache_transfer"]
    strings = [[n.lineno, n.end_lineno] for n in ast.walk(tree) if isinstance(n, ast.Expr)
               and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)
               and "self.add_kv_cache_transfer(" in n.value.value]
    return {"source": path.relative_to(ROOT).as_posix(), "active_kv_calls": calls,
            "kv_string_blocks": strings}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    checks = []
    fixtures = ROOT / "tests/fixtures/dag/v1"
    checks.append({"name": "fixture_inventory", "passed": len(list(fixtures.glob("*.graph.json"))) == 3
                   and len(list((fixtures / "invalid").glob("*.json"))) == 9})
    for path in sorted(fixtures.glob("*.graph.json")):
        expectation = path.with_name(path.name.replace(".graph.json", ".expected.json"))
        try:
            validate_expectation(read_json(path), read_json(expectation))
            checks.append({"name": path.name, "passed": True})
        except Exception as exc:
            checks.append({"name": path.name, "passed": False, "error": str(exc)})
    for path in sorted((fixtures / "invalid").glob("*.json")):
        try:
            validate_graph(read_json(path))
            checks.append({"name": path.name, "passed": False, "error": "invalid graph accepted"})
        except (ValueError, ValidationError) as exc:
            # JSON Schema ValidationError and strict JSON parse errors are expected here.
            checks.append({"name": path.name, "passed": True, "rejection": str(exc).splitlines()[0]})
    archive, inventory = audit()
    frozen_inventory = read_csv(ROOT / "configs/dag/phase1/reference-inventory.csv")
    checks.append({"name": "archive_integrity", "passed": not archive["hash_failures"] and archive["zip_sha256_passed"]})
    checks.append({"name": "inventory_matches_archive", "passed": frozen_inventory == inventory})
    sources = source_audit()
    checks.append({"name": "inactive_kv_call", "passed": not sources["active_kv_calls"] and bool(sources["kv_string_blocks"])})
    cost_probe = probe()
    checks.append({"name": "aicb_probe_reproduces_known_unit_defect", "passed": abs(cost_probe["stage_to_layer_ratio"] - 0.001) < 1e-12})
    try:
        pairs, summary = evaluate_pairs(read_csv(ROOT / "configs/dag/phase1/data-pairs.csv"),
                                         read_csv(ROOT / "configs/dag/phase1/dataset-split.csv"))
        checks.append({"name": "pair_tables_consistent", "passed": not any(p["status"] == "rejected" for p in pairs)})
    except Exception as exc:
        checks.append({"name": "pair_tables_consistent", "passed": False, "error": str(exc)})
        summary = {"accuracy_baseline": "not_passed"}
    code = int(not checks or not all(c["passed"] for c in checks))
    inputs = [p for folder in ("schemas/dag/v1", "scripts/dag_phase1", "configs/dag/phase1",
                               "tests/fixtures/dag/v1", "docs/dag/phase1")
              for p in (ROOT / folder).rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    inputs += [ROOT / item["path"] for item in archive["files"]]
    inputs += [ROOT / "baseline-data/manifest.json", ROOT / sources["source"], ROOT / cost_probe["source"],
               ROOT / "tests/test_dag_phase1_contracts.py"]
    inputs += [ROOT / path for path in (
        "vidur-alibabacloud/vidur/entities/request.py",
        "vidur-alibabacloud/vidur/entities/node.py",
        "vidur-alibabacloud/vidur/events/global_schedule_event.py",
        "vidur-alibabacloud/vidur/events/replica_stage_schedule_event.py",
        "vidur-alibabacloud/vidur/events/batch_stage_end_event.py",
        "vidur-alibabacloud/vidur/events/batch_end_event.py",
        "vidur-alibabacloud/vidur/events/base_event.py",
        "vidur-alibabacloud/vidur/scheduler/replica_stage_scheduler/replica_stage_schduler.py",
        "vidur-alibabacloud/vidur/scheduler/replica_scheduler/splitwise_replica_scheduler.py",
        "vidur-alibabacloud/vidur/execution_time_predictor/base_execution_time_predictor.py",
        "vidur-alibabacloud/vidur/execution_time_predictor/communication_time_predictor.py",
        "vidur-alibabacloud/vidur/simulator.py",
        "astra-sim-alibabacloud/astra-sim/system/collective/NcclFlowModel.cc")]
    output = run_record(args.output, "validate", inputs, code, vars(args))
    write_json(output / "validation-report.json", {"contract_acceptance": "passed" if code == 0 else "failed",
               "accuracy_baseline": summary["accuracy_baseline"],
               "stage1_overall": "passed" if code == 0 and summary["accuracy_baseline"] == "passed"
                   else "not_passed_pending_accuracy" if code == 0 else "failed", "checks": checks})
    write_json(output / "archive-audit.json", archive)
    write_json(output / "source-audit.json", sources)
    write_json(output / "aicb-unit-probe.json", cost_probe)
    print(f"checks={len(checks)}; failures={sum(not c['passed'] for c in checks)}; output={args.output}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
