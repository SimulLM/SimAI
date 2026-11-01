"""Strict I/O and run provenance shared by the phase-1 tools."""
from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
# Optional project-local installation; normal environments use requirements.txt.
LOCAL_DEPS = ROOT / ".cache/dag-phase1-deps"
if LOCAL_DEPS.is_dir():
    sys.path.insert(0, str(LOCAL_DEPS))


def read_json(path):
    def reject(value):
        raise ValueError(f"non-finite JSON constant: {value}")
    return json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=reject)


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                    allow_nan=False) + "\n", encoding="utf-8")


def read_csv(path):
    with Path(path).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(path, fields, rows):
    with Path(path).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def project_path(value):
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or "\\" in str(value) or ":" in str(value):
        raise ValueError(f"expected root-relative POSIX path: {value}")
    resolved = (ROOT / path).resolve()
    if not resolved.is_relative_to(ROOT):
        raise ValueError(f"path escapes project: {value}")
    return resolved


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def finite_nonnegative(value):
    if isinstance(value, bool):
        raise ValueError("boolean is not a duration/value")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"expected finite nonnegative value: {value}")
    return number


def run_record(output, operation, inputs, exit_code, details):
    """One record per operation; refuse overwrites within an existing run."""
    output = project_path(output)
    if not output.is_relative_to(ROOT / "results/dag/phase1") or output == ROOT / "results/dag/phase1":
        raise ValueError("output must be results/dag/phase1/<run_id>")
    output.mkdir(parents=True, exist_ok=True)
    record = output / f"{operation}-manifest.json"
    if record.exists():
        raise ValueError(f"operation already recorded: {record}")
    def git(*args):
        result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                                encoding="utf-8", errors="replace")
        return {"exit_code": result.returncode, "stdout": result.stdout,
                "stderr": result.stderr}
    dependencies = {}
    for name in ("jsonschema", "pytest"):
        try:
            dependencies[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            dependencies[name] = None
    manifest = {
        "schema_version": "1.0", "operation": operation,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "command_argv": [sys.executable, *sys.argv], "cwd": ".",
        "git_head": git("rev-parse", "HEAD"),
        "git_status": git("status", "--short"),
        "git_submodules": git("submodule", "status"),
        "git_diff": git("diff", "--no-ext-diff", "--binary"),
        "python": sys.version, "dependencies": dependencies,
        "seed": None, "seed_reason": "deterministic audit; no random generator",
        "input_sha256": {p.relative_to(ROOT).as_posix(): sha256(p) for p in sorted(set(inputs))},
        "exit_code": exit_code, "configuration": details,
    }
    write_json(record, manifest)
    (output / f"{operation}.log").write_text(
        json.dumps({"exit_code": exit_code, "details": details}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    return output
