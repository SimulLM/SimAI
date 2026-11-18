"""Run the existing phase-5 Linux build with persistent shared-library storage."""
import argparse
import os
from pathlib import Path
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="New project-local binary/evidence directory")
    args = parser.parse_args()
    if os.name != "posix":
        parser.error("run this command inside Linux/WSL")
    source = (ROOT / "scripts/dag_phase5/build_wsl.sh").read_text()
    original = "build_root=$(mktemp -d /tmp/simai-phase5-XXXXXXXX)"
    if source.count(original) != 1:
        raise ValueError("phase-5 build changed; review the persistent build adapter")
    persistent = Path.home() / ".cache/simai-phase8-builds"
    persistent.mkdir(parents=True, exist_ok=True)
    source = source.replace(original, "build_root=$(mktemp -d " + shlex.quote(str(persistent / "build-XXXXXXXX")) + ")")
    return subprocess.run(["bash", "-s", "--", args.output], input=source, text=True, cwd=ROOT).returncode


if __name__ == "__main__":
    raise SystemExit(main())
