"""Independent phase-8 audit orchestration. Uses only Python's standard library.

Run from the repository root. Each run is append-only and refuses log overwrite.
Product sources, test inputs and historical evidence are never rewritten.
"""
import argparse
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[4]
EXPECTED = "c759601e9f295240bde2efd8f4f6ee53fc4a0cdb"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def git(*args):
    p = subprocess.run(["git", *args], cwd=ROOT, capture_output=True)
    return dict(argv=["git", *args], exit_code=p.returncode,
                stdout=p.stdout.decode("utf-8", "replace"), stderr=p.stderr.decode("utf-8", "replace"))


def sources():
    items = git("ls-files", "--stage", "-z")["stdout"].split("\0")
    files = {}
    for item in items:
        if not item or item.startswith("160000 "):
            continue
        name = item.split("\t", 1)[1]
        if name.startswith("docs/dag/phase8/acceptance/"):
            continue
        p = ROOT / name
        files[name] = sha(p.read_bytes()) if p.is_file() else None
    return files


def execute(out, name, argv, *, env=None):
    folder = out / "operations" / name
    folder.mkdir(parents=True, exist_ok=False)
    save(folder / "command.json", dict(argv=list(map(str, argv)), cwd=str(ROOT),
         environment_overrides=env or {}))
    child_env = dict(os.environ)
    child_env.pop("PYTHONPATH", None)
    child_env.update(PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1",
                     PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", WANDB_MODE="disabled")
    child_env.update(env or {})
    started = time.time()
    print("START", name, flush=True)
    with (folder / "process.log").open("wb") as stream:
        try:
            code = subprocess.run(list(map(str, argv)), cwd=ROOT, env=child_env,
                                  stdout=stream, stderr=subprocess.STDOUT).returncode
            error = None
        except OSError as exc:
            code, error = None, repr(exc)
    result = dict(exit_code=code, error=error, wall_time_s=time.time() - started)
    save(folder / "process-result.json", result)
    print("END", name, json.dumps(result), flush=True)
    return result


def initialize(out):
    assert git("rev-parse", "HEAD")["stdout"].strip() == EXPECTED
    out.mkdir(parents=True, exist_ok=False)
    save(out / "identity-before.json", dict(
        actor="Codex automated acceptance; not a natural-person signature",
        tested_commit=EXPECTED, branch=git("branch", "--show-current"),
        git_status=git("status", "--short"),
        git_status_without_submodules=git("status", "--short", "--ignore-submodules=all"),
        submodules=git("submodule", "status"), submodule_gitlinks=git("ls-tree", "HEAD", "SimCCL", "aicb", "ns-3-alibabacloud"),
        platform=platform.platform(), python=sys.version, source_sha256=sources()))


def audit(out):
    base = ROOT / "docs/dag/phase8/artifacts"
    rows, scores = [], []
    for line in (base / "SHA256SUMS").read_text().splitlines():
        expected, filename = line.split()
        path = base / filename
        mismatches, missing, verified = [], [], 0
        source_checked, source_bad, source_missing = 0, [], []
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            bad_crc = z.testzip()
            for n in sorted(names):
                if not n.endswith(("run-manifest.json", "DELIVERY.json")):
                    continue
                d = json.loads(z.read(n))
                if not isinstance(d, dict):
                    continue
                prefix = n[:-len(n.rsplit("/", 1)[-1])]
                if n.endswith("run-manifest.json") and "/phase4/" not in n:
                    for f, h in d.get("source_sha256", {}).items():
                        snapshot = "tested-source/" + f
                        if snapshot not in names:
                            source_missing.append(snapshot)
                        else:
                            source_checked += 1
                            if sha(z.read(snapshot)) != h:
                                source_bad.append(snapshot)
                for f, h in d.get("artifact_sha256", {}).items():
                    candidate = prefix + f
                    # Early mechanism DELIVERY maps paths relative to result_path;
                    # later bundles use project-relative paths. Both are explicit.
                    if candidate not in names and n == "DELIVERY.json" and d.get("result_path"):
                        candidate = d["result_path"].rstrip("/") + "/" + f
                    if candidate not in names:
                        missing.append(candidate)
                    else:
                        verified += 1
                        if sha(z.read(candidate)) != h:
                            mismatches.append(candidate)
            # Recalculate directly from numeric prediction/reference fields, not reported errors.
            for n in sorted(names):
                if not n.endswith("request-comparison.csv") or "/cases/" in n:
                    continue
                data = list(csv.DictReader(io.StringIO(z.read(n).decode("utf-8-sig"))))
                if not data:
                    continue
                fields = set(data[0])
                if {"reference_s", "old_s", "revised_cost_s"} <= fields:
                    selected = [r for r in data if r.get("split") == "validation"]
                    modes, ref = ("old", "same_cost", "revised_cost"), "reference_s"
                    value = lambda r, m: float(r[m + "_s"])
                elif {"reference_e2e_s", "legacy_e2e_s", "dag_expanded_e2e_s"} <= fields:
                    selected = [r for r in data if r.get("role") == "validation"]
                    modes, ref = ("legacy", "dag_expanded"), "reference_e2e_s"
                    value = lambda r, m: float(r[m + "_e2e_s"])
                else:
                    continue
                errors = {m: [abs(value(r, m) - float(r[ref])) / abs(float(r[ref])) for r in selected] for m in modes}
                checks = []
                for r in selected:
                    for m in modes:
                        key = m + "_relative_error"
                        if key in r:
                            expected_error = abs(value(r, m) - float(r[ref])) / abs(float(r[ref]))
                            checks.append(math.isclose(expected_error, float(r[key]), abs_tol=1e-12, rel_tol=1e-10))
                scores.append(dict(archive=filename, csv=n, validation_samples=len(selected),
                    independently_computed_mean_relative_errors={m: math.fsum(v)/len(v) if v else None for m, v in errors.items()},
                    reported_errors_match=all(checks), checked_errors=len(checks)))
        rows.append(dict(archive=filename, sha256=sha(path.read_bytes()), expected_sha256=expected,
            archive_hash_matches=sha(path.read_bytes()) == expected, crc_error=bad_crc,
            internal_hashes_checked=verified, internal_hash_mismatches=mismatches, missing_files=missing,
            source_hashes_checked=source_checked, source_hash_mismatches=source_bad, missing_source_snapshots=source_missing))
    save(out / "historical-audit.json", dict(archives=rows, recomputed_scores=scores,
        passed=all(r["archive_hash_matches"] and not r["crc_error"] and not r["internal_hash_mismatches"] and not r["missing_files"]
            and not r["source_hash_mismatches"] and not r["missing_source_snapshots"] for r in rows)
            and all(r["reported_errors_match"] for r in scores)))


def environment(out, cache):
    base_python = "D:/Environment/Python312/python.exe"
    for name in ("env-a", "env-b"):
        dest = cache / name
        if not (dest / "Scripts/python.exe").exists():
            result = execute(out, "create-" + name, [base_python, "-m", "venv", dest])
            if result["exit_code"] != 0:
                continue
        py = dest / "Scripts/python.exe"
        execute(out, "install-" + name, [py, "-m", "pip", "install", "-r", "scripts/dag_phase8/requirements.txt", "--disable-pip-version-check"])
        execute(out, "freeze-" + name, [py, "-m", "pip", "freeze", "--all"])
        execute(out, "check-" + name, [py, "-m", "pip", "check"])


def run(out, cache, which):
    py = cache / "env-a/Scripts/python.exe"
    if which == "full":
        execute(out, "full-acceptance", [py, "scripts/dag_phase8/main.py", "--output", out / "full", "--repro-python", cache / "env-b/Scripts/python.exe"])
    elif which in ("mechanism", "original", "expanded", "holdout"):
        for family, spec in (("original", "mechanism-experiment"), ("expanded", "mechanism-expanded"), ("holdout", "mechanism-fcfs-holdout")):
            if which != "mechanism" and family != which:
                continue
            for policy in ("submission", "fcfs"):
                execute(out, family + "-" + policy, [py, "scripts/dag_phase8/mechanism_experiment.py",
                    "--spec", f"configs/dag/phase8/{spec}.json", "--ready-queue-policy", policy,
                    "--output", out / (family + "-" + policy)])
            execute(out, family + "-comparison", [py, "scripts/dag_phase8/queue_policy_comparison.py",
                "--before-run", out / (family + "-submission"), "--after-run", out / (family + "-fcfs"),
                "--output", out / (family + "-comparison")])
    elif which == "prepare-dense":
        execute(out, which, [py, "scripts/dag_phase8/simulated_reference.py", "--output", out / "dense", "--prepare"])
    elif which == "score-dense":
        execute(out, which, [py, "scripts/dag_phase8/simulated_reference.py", "--output", out / "dense",
            "--backend-evidence", out / "dense/backend-reference"])
    elif which == "regression":
        env = {"PYTHONPATH": os.pathsep.join((str(ROOT), str(ROOT / "vidur-alibabacloud")))}
        execute(out, "regression-retry", [py, "-m", "pytest", "tests/test_dag_phase1_contracts.py", "tests/dag", "-q",
            "-p", "no:cacheprovider", "--basetemp", out / "retry-pytest-tmp", "--junitxml", out / "retry-pytest.xml"], env=env)


def checkpoint(out):
    before = json.loads((out / "identity-before.json").read_text(encoding="utf-8"))
    after = sources()
    save(out / "identity-after.json", dict(tested_commit=git("rev-parse", "HEAD"),
        branch=git("branch", "--show-current"), source_sha256=after,
        changed_tested_files=[p for p in sorted(set(before["source_sha256"]) | set(after)) if before["source_sha256"].get(p) != after.get(p)]))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("init", "audit", "environment", "full", "mechanism", "original", "expanded", "holdout", "prepare-dense", "score-dense", "regression", "checkpoint"))
    p.add_argument("--run", required=True, type=Path)
    p.add_argument("--cache", type=Path, default=Path(".cache/phase8-acceptance-20261119"))
    args = p.parse_args()
    out, cache = (ROOT / args.run).resolve(), (ROOT / args.cache).resolve()
    if not out.is_relative_to(ROOT / "results/dag/phase8") or out == ROOT / "results/dag/phase8":
        p.error("run must be a new child of results/dag/phase8")
    if not cache.is_relative_to(ROOT / ".cache"):
        p.error("cache must be below project .cache")
    if args.action == "init": initialize(out)
    elif args.action == "audit": audit(out)
    elif args.action == "environment": environment(out, cache)
    elif args.action == "checkpoint": checkpoint(out)
    else: run(out, cache, args.action)
