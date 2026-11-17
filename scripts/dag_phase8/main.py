"""Phase-8 joint regression, scale, frozen accuracy and fresh-environment replay."""
import argparse
from hashlib import sha256
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "vidur-alibabacloud")]

from scripts.dag_phase4.main import hashes, synthetic_profiles, write_csv, write_json
from scripts.dag_phase8.accuracy import evaluate, historical_component_evidence
from scripts.dag_phase8.joint import run_case
from scripts.dag_phase8.overhead import measure
from schemas.dag.v1.io import read_json


def source_hashes():
    folders = ("schemas/dag", "vidur-alibabacloud/vidur", "configs/dag", "scripts/dag_phase1",
               "scripts/dag_phase2", "scripts/dag_phase3", "scripts/dag_phase4", "scripts/dag_phase5",
               "scripts/dag_phase6", "scripts/dag_phase7", "scripts/dag_phase8", "tests/dag",
               "tests/fixtures/dag", "docs/dag/phase8")
    files = {p for folder in folders for p in (ROOT / folder).rglob("*") if p.is_file()
             and p.suffix in (".py", ".json", ".csv", ".txt", ".md") and "__pycache__" not in p.parts}
    files.update((ROOT / "tests/test_dag_phase1_contracts.py", ROOT / "baseline-data/manifest.json",
                  ROOT / "docs/dag/phase5/artifacts/20261113-phase5-delivery.zip"))
    return hashes(ROOT, files)


def input_hashes(dataset):
    from common import project_path
    files = {dataset}
    data = read_json(dataset)
    if data.get("parameter_freeze"):
        files.add(project_path(data["parameter_freeze"]["path"]))
    for sample in data["samples"]:
        for key in ("reference_record", "old_record", "same_cost_record", "revised_cost_record"):
            path = project_path(sample[key])
            files.add(path)
            files.update(project_path(item["path"]) for item in read_json(path)["evidence"])
    return hashes(ROOT, files)


def regression(output):
    command = [sys.executable, "-m", "pytest", "tests/test_dag_phase1_contracts.py", "tests/dag", "-q",
               "-p", "no:cacheprovider", "--basetemp", str(output / "pytest-tmp"),
               "--junitxml", str(output / "pytest.xml")]
    write_json(output / "pytest-command.json", command)
    with (output / "pytest.log").open("w", encoding="utf-8") as stream:
        code = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT).returncode
    summary = ET.parse(output / "pytest.xml").getroot().find("testsuite").attrib
    return dict(exit_code=code, **summary)


def replay(output, python, dataset, expected):
    destination = output / "fresh-environment-replay"
    command = [str(python.resolve()), str(Path(__file__).resolve()), "--output", str(destination),
               "--validation-data", str(dataset), "--smoke"]
    env = dict(os.environ, PYTHONPATH=os.pathsep.join((str(ROOT / "vidur-alibabacloud"), str(ROOT))),
               PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", WANDB_MODE="disabled")
    write_json(output / "reproduction-command.json", command)
    with (output / "reproduction.log").open("w", encoding="utf-8") as stream:
        code = subprocess.run(command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT).returncode
    report = read_json(destination / "acceptance-report.json")
    manifest = read_json(destination / "run-manifest.json")
    observed = report["joint_cases"][0]
    keys = ("task_count", "event_count", "graph_count", "routing_count", "request_count")
    passed = (code in (0, 2) and report["functional_status"] == "passed" and
              manifest["environment"]["prefix"] != sys.prefix and
              all(observed[key] == expected[key] for key in keys) and
              abs(observed["simulated_final_time_s"] - expected["simulated_final_time_s"]) <= 1e-12)
    result = dict(status="passed" if passed else "failed", child_exit_code=code,
                  isolated_environment=manifest["environment"], matching_fields=list(keys),
                  independent_person_status="pending_external_signoff")
    write_json(output / "reproduction-report.json", result)
    frozen = subprocess.run([str(python.resolve()), "-m", "pip", "freeze"], capture_output=True,
                            encoding="utf-8", errors="replace", env=env)
    if frozen.returncode != 0:
        raise RuntimeError("cannot record clean-environment dependency versions")
    (output / "fresh-environment-requirements.txt").write_text(frozen.stdout, encoding="utf-8")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--validation-data", type=Path, default=ROOT / "configs/dag/phase8/validation.json")
    parser.add_argument("--repro-python", type=Path, help="Python from a separate clean virtual environment")
    parser.add_argument("--smoke", action="store_true", help="single joint CLI replay; not full acceptance")
    args = parser.parse_args(argv)
    output = (ROOT / args.output).resolve()
    dataset = (ROOT / args.validation_data).resolve()
    if not output.is_relative_to(ROOT / "results/dag/phase8") or output == ROOT / "results/dag/phase8":
        parser.error("output must be a new directory below results/dag/phase8")
    if not dataset.is_relative_to(ROOT):
        parser.error("validation dataset must be inside the project")
    output.mkdir(parents=True, exist_ok=False)
    os.environ.update(PYTHONPATH=os.pathsep.join((str(ROOT / "vidur-alibabacloud"), str(ROOT), os.environ.get("PYTHONPATH", ""))),
                      PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", WANDB_MODE="disabled", PYTHONDONTWRITEBYTECODE="1")
    started = time.perf_counter()
    manifest = dict(command=[sys.executable, str(Path(__file__)), *(argv if argv is not None else sys.argv[1:])], seed=42,
        environment=dict(python=sys.version, executable=sys.executable, prefix=sys.prefix),
        dependencies={name: importlib.metadata.version(name)
                      for name in sorted({d.metadata["Name"] for d in importlib.metadata.distributions()})})
    for key, cmd in (("head", ["rev-parse", "HEAD"]), ("status", ["status", "--short"]), ("diff", ["diff", "--binary", "HEAD"])):
        result = subprocess.run(["git", *cmd], cwd=ROOT, capture_output=True, encoding="utf-8", errors="replace")
        manifest["git_" + key] = dict(exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr)
    report = dict(functional_status="failed", accuracy_status="not_evaluated", joint_cases=[],
                  full_regression_run=not args.smoke, scope="smoke" if args.smoke else "full_phase8",
                  reproduction_status="not_run", independent_person_status="pending_external_signoff",
                  hardware_accuracy_claim=False, overall_project_acceptance="pending")
    code = 1
    try:
        manifest["source_sha256"] = source_hashes()
        manifest["input_sha256"] = input_hashes(dataset)
        print("Checking frozen accuracy records and historical component evidence", flush=True)
        accuracy = evaluate(output / "accuracy", dataset)
        report["accuracy_status"] = accuracy["status"]
        report["hardware_accuracy_claim"] = accuracy["hardware_accuracy_claim"]
        historical_component_evidence(output)
        profiles = output / "synthetic-profiles"
        synthetic_profiles(profiles)
        for tier, count in (("small", 1),) if args.smoke else (("small", 1), ("medium", 2), ("large", 4)):
            print(f"Running joint scale {tier}: {count} requests", flush=True)
            report["joint_cases"].append(run_case(output, profiles, "scale-" + tier, [(0, 8, 2)] * count))
        if not args.smoke:
            print("Running joint destination backpressure", flush=True)
            report["joint_cases"].append(run_case(output, profiles, "joint-backpressure", [(0, 8, 8)] * 4,
                                                require_backpressure=True))
            scales = [{key: row[key] for key in ("name", "request_count", "task_count", "event_count", "graph_count",
                       "routing_count", "wall_time_s", "event_queue_peak", "peak_rss_bytes", "simulated_final_time_s")}
                      for row in report["joint_cases"][:3]]
            write_csv(output / "scale-overhead.csv", scales)
            print("Measuring export snapshot overhead", flush=True)
            measure(output)
            print("Running complete phase 1-8 regression", flush=True)
            report["regression"] = regression(output)
            if args.repro_python:
                print("Replaying in a separate clean environment", flush=True)
                report["reproduction_status"] = replay(output, args.repro_python, dataset, report["joint_cases"][0])["status"]
        if source_hashes() != manifest["source_sha256"] or input_hashes(dataset) != manifest["input_sha256"]:
            raise RuntimeError("source or frozen inputs changed during acceptance")
        if all(row["passed"] for row in report["joint_cases"]) and report.get("regression", {}).get("exit_code", 0) == 0:
            report["functional_status"] = "passed"
            code = 0 if accuracy["status"] == "passed" and report["reproduction_status"] == "passed" and not args.smoke else 2
        if report["reproduction_status"] == "failed" or accuracy["status"] == "rejected":
            code = 1
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        write_json(output / "operation-error.json", dict(error=report["error"], traceback=traceback.format_exc()))
    report["exit_code"] = code
    write_json(output / "acceptance-report.json", report)
    manifest.update(exit_code=code, wall_time_s=time.perf_counter() - started)
    manifest["artifact_sha256"] = hashes(output, {p for p in output.rglob("*") if p.is_file()
        and not {"pytest-tmp", "predictor-cache"}.intersection(p.relative_to(output).parts)})
    write_json(output / "run-manifest.json", manifest)
    print(json.dumps(dict(functional_status=report["functional_status"], accuracy_status=report["accuracy_status"],
                         reproduction_status=report["reproduction_status"], exit_code=code)), flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
