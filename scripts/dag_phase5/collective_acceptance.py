"""Build a phase-1-compatible evidence overlay from WSL simulator runs."""
import json
import math
import shutil
import subprocess
import time

from collective import ROOT, SIZES, TOPOLOGY, digest, prepare, run, save_json
from collective_cli import MODEL, run as run_cli_collective, write_csv


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def project_relative(path):
    return path.relative_to(ROOT).as_posix()


def write_record(case, version, inputs, folder, measurement, kind, files, value, wall_time=None):
    workload = inputs / f"{case}.txt"
    topology = inputs / TOPOLOGY
    # Shared configuration is hashed by the run manifest and record identity.
    # Per-record evidence stays sample-specific so split admission can detect leakage.
    files = [workload, *files]
    record = folder / f"{kind}-record.json"
    save_json(record, {
        "model": MODEL, "hardware": "8xH20, single host, NVLink 300 GB/s, NIC 25 GB/s",
        "input_sha256": digest(workload), "topology_sha256": digest(topology), "batch": 1,
        "tp": 8, "pp": 1, "ep": 1, "dtype": "fp16", "metric": "tp_allreduce_forward",
        "metric_definition": "Single forward AllReduce service interval for the frozen payload and rank group, excluding CPU launch/skew",
        "run_id": project_relative(measurement), "version": version, "group_id": f"micro_allreduce_{case}",
        "nature": "simulated", "verification": "verified", "raw_value": value,
        "raw_unit": "us" if kind == "reference" else "s",
        "conversion_to_s": 1e-6 if kind == "reference" else 1,
        "unit_evidence": ("astra-sim/workload/Layer.cc: fwd total comm divides ticks by FREQ"
                          if kind == "reference" else "Backend forward communication converted from us or DAG end_at_s minus start_at_s"),
        "evidence": [{"path": project_relative(path), "sha256": digest(path)} for path in files],
        "wall_time_s": wall_time,
    })
    return project_relative(record)


def evaluate_collectives(output, binaries, refine_from=None):
    output = output / "collective-evidence"
    output.mkdir()
    for name in ("build-inputs.log", "build-status.txt", "analytical-build.log", "ns3-build.log", "binaries.sha256"):
        shutil.copyfile(binaries / name, output / name)
    for line in (output / "binaries.sha256").read_text(encoding="utf-8").splitlines():
        expected, name = line.split()
        if digest(binaries / name) != expected:
            raise ValueError(f"binary hash mismatch: {name}")
    source = subprocess.check_output(["git", "-c", f"safe.directory={ROOT}", "rev-parse", "HEAD"],
                                     cwd=ROOT, text=True).strip()
    inputs = output / "inputs"
    sizes = dict(SIZES)
    if refine_from:
        prior = refine_from / "collective-evidence"
        raw = read(prior / "validation/ns3-reference/collective.json")["values"][0] * 1e-6
        old = read(prior / "validation/legacy/collective.json")["latency_s"]
        revised = read(prior / "validation/revised-cost/collective.json")["latency_s"]
        if abs(revised - raw) <= abs(old - raw):
            raise ValueError("refinement requires a documented regression on the first holdout")
        save_json(output / "prior-validation.json", {
            "run": project_relative(refine_from), "payload_bytes": sizes["validation"],
            "reference_s": raw, "legacy_s": old, "scaled_s": revised,
            "legacy_error_s": abs(old - raw), "scaled_error_s": abs(revised - raw),
            "disposition": "Previous validation retained as a failed experiment; excluded from scoring the refinement.",
        })
        sizes["validation"] = 32 * 1024**2
    prepare(inputs, sizes)
    for backend in ("analytical", "ns3"):
        run(inputs, binaries, backend, "smoke", output / f"smoke-{backend}")
    pairs, splits = [], []
    config = output / "calibration.json"
    for case in SIZES:
        folder = output / case
        reference = folder / "ns3-reference"
        run(inputs, binaries, "ns3", case, reference)
        ref = read(reference / "collective.json")
        old, same, revised = (folder / name for name in ("legacy", "same-cost", "revised-cost"))
        for path, mode in ((old, "legacy"), (same, "dag_expanded")):
            run_cli_collective(inputs, binaries, case, "simai_analytical", mode, path)
        ref_cli = folder / "ns3-expanded"
        run_cli_collective(inputs, binaries, case, "simai_simulation", "dag_expanded", ref_cli)
        observed_ns3 = read(ref_cli / "collective.json")["latency_s"]
        if not math.isclose(observed_ns3, ref["values"][0] * 1e-6, rel_tol=1e-8, abs_tol=1e-12):
            raise ValueError("direct ns-3 reference and CLI backend service do not match")
        old_s = read(old / "collective.json")["latency_s"]
        same_s = read(same / "collective.json")["latency_s"]
        if old_s <= 0 or not math.isclose(old_s, same_s, abs_tol=1e-12):
            raise ValueError("same-cost path changed collective service time")
        if case == "calibration":
            reference_s = ref["values"][0] * 1e-6
            # Keep the analytical throughput slope and estimate only a fixed
            # overhead on the original calibration input after scale regression.
            parameters = {"offset_s": max(0, reference_s - old_s)} if refine_from else {
                "scale": reference_s / old_s,
            }
            save_json(config, {"tp_cost_calibration": {
                "model": MODEL, "tp": 8, "pp": 1, **parameters,
                "evidence": project_relative(reference / "collective.json"),
                "topology_sha256": digest(inputs / TOPOLOGY), "config_sha256": digest(inputs / "SimAI.conf"),
            }})
            save_json(output / "parameter-freeze.json", {"calibration_sha256": digest(config),
                                                         "validation_input_sha256": digest(inputs / "validation.txt")})
        frozen = read(output / "parameter-freeze.json")
        if (frozen["calibration_sha256"] != digest(config) or
                frozen["validation_input_sha256"] != digest(inputs / "validation.txt")):
            raise ValueError("calibration changed after freeze")
        started = time.perf_counter()
        run_cli_collective(inputs, binaries, case, "simai_analytical", "dag_expanded", revised, config)
        wall_time = time.perf_counter() - started
        record_paths = {"reference_record": write_record(
            case, f"ns3:{source}:{digest(binaries / 'SimAI_simulator')}", inputs, folder, reference,
            "reference", [reference / name for name in ("collective.json", "command.json", "process.log", ref["csv"])],
            ref["values"][0])}
        for kind, field, path in (("old", "old_record", old), ("same-cost", "same_cost_record", same),
                                  ("revised-cost", "revised_cost_record", revised)):
            data = read(path / "collective.json")
            native = path / data["native"]
            evidence = [path / "collective.json", path / data["backend_csv"], path / data["workload"],
                        native / "config.json", native / "execution-summary.json",
                        native.parent / "command.json", native.parent / "process.log"]
            if kind != "old":
                evidence.append(native / "timeline.csv")
            if kind == "revised-cost":
                evidence.extend((config, output / "parameter-freeze.json"))
            record_paths[field] = write_record(case, f"analytical:{source}:{data['binary_sha256']}",
                                               inputs, folder, path, kind, evidence, data["latency_s"],
                                               wall_time if kind == "revised-cost" else None)
        pair = f"micro_allreduce_{case}"
        adjustment = "fixed TP service offset" if refine_from else "TP service ratio"
        pairs.append(dict(pair_id=pair, group_id=pair, status="eligible", reason="", **record_paths,
                          attribution=f"Same-cost DAG preserves service. Revised analytical cost uses a frozen {adjustment}."))
        splits.append(dict(group_id=pair, split=case, reason="Frozen distinct payload before calibration"))
    write_csv(output / "data-pairs.csv", pairs)
    write_csv(output / "dataset-split.csv", splits)
    return output
