"""Run phase-1 pytest with project-local temp files and capture the handoff evidence."""
import argparse
import subprocess
import sys

from common import ROOT, project_path, run_record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = project_path(args.output)
    if (output / "pytest-manifest.json").exists():
        raise ValueError("pytest operation already recorded")
    if not output.is_relative_to(ROOT / "results/dag/phase1") or output == ROOT / "results/dag/phase1":
        raise ValueError("output must be results/dag/phase1/<run_id>")
    output.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, "-m", "pytest", "tests/test_dag_phase1_contracts.py", "-q",
               "--basetemp", str(output / "pytest-tmp"), "--junitxml", str(output / "pytest.xml")]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    inputs = [ROOT / "tests/test_dag_phase1_contracts.py"]
    inputs += [p for folder in ("scripts/dag_phase1", "schemas/dag/v1", "tests/fixtures/dag/v1")
               for p in (ROOT / folder).rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    run_record(args.output, "pytest", inputs, result.returncode, {"pytest_argv": command})
    (output / "pytest.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    print(result.stdout)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
