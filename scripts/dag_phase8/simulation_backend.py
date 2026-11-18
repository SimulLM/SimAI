"""Generate fresh CPU ns-3/analytical outputs, without importing the DAG runtime."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.dag_phase5.collective import digest, run, save_json


def generate(inputs, binaries, output):
    output.mkdir(parents=True, exist_ok=False)
    frozen = json.loads((inputs / "frozen-inputs.json").read_text())
    build_root = Path((binaries / "build-root.txt").read_text().strip())
    libraries = build_root / "astra-sim-alibabacloud/extern/network_backend/ns3-interface/simulation/build/lib"
    if not libraries.is_dir():
        raise ValueError("ns-3 build libraries are missing; rebuild with build_wsl.sh")
    os.environ["LD_LIBRARY_PATH"] = str(libraries) + os.pathsep + os.environ.get("LD_LIBRARY_PATH", "")
    expected = {}
    for line in (binaries / "binaries.sha256").read_text().splitlines():
        value, name = line.split()
        if digest(binaries / name) != value:
            raise ValueError(f"binary checksum mismatch: {name}")
        expected[name] = value
    records = []
    for case, payload in frozen["payload_bytes"].items():
        for backend in ("analytical", "ns3"):
            print(f"Generating {backend}: {case}, {payload} bytes", flush=True)
            destination = output / case / backend
            run(inputs, binaries, backend, case, destination)
            records.append(dict(case=case, backend=backend, payload_bytes=payload,
                                collective_sha256=digest(destination / "collective.json")))
    save_json(output / "backend-manifest.json", dict(
        reference_nature="simulated", fresh_execution=True, hardware_accuracy_claim=False,
        binaries_sha256=expected, frozen_inputs_sha256=digest(inputs / "frozen-inputs.json"),
        build_evidence_sha256={name: digest(binaries / name) for name in
                              ("build-inputs.log", "analytical-build.log", "ns3-build.log", "build-status.txt", "binaries.sha256")},
        library_directory=str(libraries),
        library_sha256={p.name: digest(p) for p in sorted(libraries.glob("libns3*.so"))},
        records=records,
        artifact_sha256={p.relative_to(output).as_posix(): digest(p)
                         for p in sorted(output.rglob("*")) if p.is_file()}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--binaries", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    generate(args.inputs.resolve(), args.binaries.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
