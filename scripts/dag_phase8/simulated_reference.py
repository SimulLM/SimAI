"""Controlled request E2E comparison against fresh ns-3 communication references.

The compute model and scheduler are held fixed. This is a communication-model
experiment, not an independent full-model or hardware accuracy benchmark.
"""
import argparse
import csv
from hashlib import md5, sha256
import importlib.metadata
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "vidur-alibabacloud")]

from scripts.dag_phase4.main import cli_command, hashes, run_cli, synthetic_profiles, write_csv, write_json
from scripts.dag_phase5.collective import ANALYTICAL_PRICING, TOPOLOGY, collective_times, prepare
from scripts.dag_phase8.accuracy import digest, evaluate

EXPERIMENT = ROOT / "configs/dag/phase8/simulated-reference-experiment.json"
PREFIX = "--random_forrest_execution_time_predictor_config_"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def relative(path):
    return Path(path).relative_to(ROOT).as_posix()


def option(command, name, value):
    if name in command:
        command[command.index(name) + 1] = str(value)
    else:
        command.extend((name, str(value)))


def prepare_experiment(output):
    output.mkdir(parents=True, exist_ok=False)
    specification = read(EXPERIMENT)
    write_json(output / "experiment.json", specification)
    sizes = {s["id"]: s["prefill_tokens"] * 4096 * 2 for s in specification["samples"]}
    # The original predictor rounds single-token Decode batches to eight tokens.
    sizes["decode"] = 8 * 4096 * 2
    prepare(output / "inputs", sizes)
    synthetic_profiles(output / "profiles", tp_sizes=(8,), network_devices=8)
    files = {p for name in ("profiles", "inputs") for p in (output / name).rglob("*") if p.is_file()}
    files.add(output / "experiment.json")
    write_json(output / "experiment-freeze.json", dict(
        status="prepared_before_reference_generation", primary_metric=specification["primary_metric"],
        input_sha256=hashes(output, files), specification_sha256=digest(EXPERIMENT)))


def validate_backend(output, backend):
    initial = read(output / "experiment-freeze.json")
    for name, value in initial["input_sha256"].items():
        if digest(output / name) != value:
            raise ValueError(f"frozen experiment input changed: {name}")
    manifest = read(backend / "backend-manifest.json")
    if not manifest["fresh_execution"] or manifest["frozen_inputs_sha256"] != digest(output / "inputs/frozen-inputs.json"):
        raise ValueError("backend does not match this freshly prepared experiment")
    for name, value in manifest["artifact_sha256"].items():
        if digest(backend / name) != value:
            raise ValueError(f"backend evidence checksum mismatch: {name}")
    sizes = read(output / "inputs/frozen-inputs.json")["payload_bytes"]
    entries = {(r["case"], r["backend"]): r for r in manifest["records"]}
    if set(entries) != {(case, kind) for case in sizes for kind in ("analytical", "ns3")}:
        raise ValueError("missing or unexpected backend case")
    for (case, kind), entry in entries.items():
        folder = backend / case / kind
        result = read(folder / "collective.json")
        [raw_us] = collective_times(folder / result["csv"])
        if (entry["payload_bytes"] != sizes[case] or result["unit"] != "us" or
                result["values"] != [raw_us] or entry["collective_sha256"] != digest(folder / "collective.json")):
            raise ValueError("backend payload, units or collective values do not match")
    return manifest


def seed_cache(output, backend, destination, kind):
    """Replay exact raw simulator CSV bytes through the unmodified CLI cache path."""
    destination.mkdir(parents=True)
    files = []
    sizes = read(output / "inputs/frozen-inputs.json")["payload_bytes"]
    topo = str((output / "inputs" / TOPOLOGY).resolve())
    conf = str((output / "inputs/SimAI.conf").resolve())
    bandwidth = {"-nv": 300.0, "-nic": 25.0, "-n_p_s": 8}
    for case, payload in sizes.items():
        tokens = payload // (4096 * 2)
        stem = "analytical_EndToEnd_" if kind == "analytical" else "ncclFlowModel_EndToEnd_"
        source_folder = backend / case / kind
        source = source_folder / read(source_folder / "collective.json")["csv"]
        # Trace replay retains float-valued Prefill counts; Decode uses integers.
        # The original cache key preserves that representation despite equal bytes.
        for token_text in (str(tokens), str(float(tokens))):
            workload = md5(f"layer01ALLREDUCE4096{token_text}2:integer-bytes".encode()).hexdigest()
            identity = f"{workload}_{topo}_{conf}"
            if kind == "analytical":
                identity += f"_8_{bandwidth}"
            target = destination / (stem + md5(identity.encode()).hexdigest() + ".csv")
            shutil.copyfile(source, target)
            files.append(dict(case=case, payload_bytes=payload, token_representation=token_text,
                              source=relative(source), target=relative(target), sha256=digest(source)))
    write_json(destination / "replay-provenance.json", dict(
        mode="exact_raw_output_replay", backend=kind, files=files,
        note="Fresh CPU simulator execution is recorded separately; the CLI consumes unchanged CSV bytes."))


def run_prediction(output, backend, sample, role, calibration=None):
    folder = output / "runs" / sample["id"] / role
    folder.mkdir(parents=True)
    trace = folder / "requests.csv"
    write_csv(trace, [dict(arrived_at=0, num_prefill_tokens=sample["prefill_tokens"],
                           num_decode_tokens=sample["decode_tokens"])])
    kind = "ns3" if role == "reference" else "analytical"
    seed_cache(output, backend, folder / "backend", kind)
    mode = "legacy" if role in ("reference", "old") else "dag_expanded"
    command = cli_command(mode, folder / "cli", output / "profiles", trace, tp=8)
    for key, value in {
        "--replica_config_device": "h20", "--replica_config_network_device": "h20_dgx",
        "--trace_request_generator_config_max_tokens": 8192,
        "--sarathi_scheduler_config_chunk_size": 8192, "--sarathi_scheduler_config_batch_size_cap": 1,
        PREFIX + "backend": "simai_simulation" if kind == "ns3" else "simai_analytical",
        PREFIX + "simai_dir": folder / "backend", PREFIX + "simai_simulation_topo": output / "inputs" / TOPOLOGY,
        PREFIX + "simai_simulation_config": output / "inputs/SimAI.conf",
        PREFIX + "prediction_max_batch_size": 1, PREFIX + "prediction_max_tokens_per_request": 8192,
        PREFIX + "prediction_max_prefill_chunk_size": 8192, PREFIX + "kv_cache_prediction_granularity": 1024,
        PREFIX + "nccl_cpu_launch_overhead_ms": 0, PREFIX + "nccl_cpu_skew_overhead_per_device_ms": 0,
        **{PREFIX + key: value for key, value in ANALYTICAL_PRICING.items()},
    }.items():
        option(command, key, value)
    if calibration:
        option(command, "--dag_resource_config", calibration)
    summary, native = run_cli(command, folder / "cli")
    if (summary["status"] != "completed" or len(summary["requests"]) != 1 or
            not summary["requests"][0]["completed"] or
            summary["requests"][0]["num_processed_tokens"] != sample["prefill_tokens"] + sample["decode_tokens"]):
        raise ValueError("request did not complete with the frozen token counts")
    known_payloads = set(read(output / "inputs/frozen-inputs.json")["payload_bytes"].values())
    generated = list((folder / "backend/tmp_simai_inference_workload").glob("*.txt"))
    if len(generated) != 2:
        raise ValueError("expected exactly the Prefill and rounded Decode workloads")
    for path in generated:
        lines = path.read_text().splitlines()
        payload = int(lines[2].split()[4])
        expected_case = next((name for name, size in read(output / "inputs/frozen-inputs.json")["payload_bytes"].items()
                              if size == payload), None)
        if payload not in known_payloads or lines != (output / "inputs" / (expected_case + ".txt")).read_text().splitlines():
            raise ValueError("generated communication workload differs from the reference input")
    for item in read(folder / "backend/replay-provenance.json")["files"]:
        if digest(ROOT / item["target"]) != item["sha256"]:
            raise ValueError("raw simulator replay bytes changed")
    request = summary["requests"][0]
    with (native / "request_metrics.csv").open(encoding="utf-8", newline="") as stream:
        [metrics] = list(csv.DictReader(stream))
    result = dict(e2e_s=request["completed_at"] - request["arrived_at"],
                  ttft_s=float(metrics["prefill_e2e_time"]),
                  tpot_s=float(metrics["decode_time_execution_plus_preemption_normalized"]),
                  native=relative(native), request_tokens=request["num_processed_tokens"], mode=mode, backend=kind)
    if not math.isclose(result["e2e_s"], float(metrics["request_e2e_time"]), abs_tol=1e-12):
        raise ValueError("request E2E metric differs from completion minus arrival")
    if mode == "dag_expanded":
        graphs = [read(p) for p in (native / "graphs").glob("*.graph.json")]
        result["tp_task_count"] = sum(t["metadata"].get("communication_type") == "tp" for g in graphs for t in g["tasks"])
    write_json(folder / "prediction.json", result)
    return result


def write_record(output, sample, role, prediction, cost_hash, freeze_hash=None):
    folder = output / "runs" / sample["id"] / role
    native = ROOT / prediction["native"]
    # Shared compute/topology/backend definitions are frozen once in the run
    # manifest. Per-record evidence is the actual, sample-specific CLI execution.
    evidence = [folder / "requests.csv", folder / "prediction.json", native / "execution-summary.json",
                native / "request_metrics.csv", folder / "cli/command.json"]
    record = dict(model=read(output / "experiment.json")["model"],
        hardware="8xH20 logical topology; shared synthetic compute; CPU communication simulation",
        input_sha256=digest(folder / "requests.csv"), topology_sha256=digest(output / "inputs" / TOPOLOGY),
        batch=1, tp=8, pp=1, ep=1, dtype="fp16", metric="request_e2e",
        metric_definition="Single request completion minus arrival; fixed synthetic compute and scheduler; ns3 communication reference",
        run_id=relative(folder), version=read(output / "source-identity.json")["runtime_sha256"],
        group_id="dense_tp8_" + sample["id"], nature="simulated", verification="verified",
        raw_value=prediction["e2e_s"], raw_unit="s", conversion_to_s=1.0,
        unit_evidence="Original CLI execution-summary.json completed_at minus arrived_at; Simulator time is seconds",
        evidence=[dict(path=relative(p), sha256=digest(p)) for p in evidence], cost_config_sha256=cost_hash,
        reference_scope="conditional_communication_model_comparison", compute_nature="synthetic",
        shared_reference_definition=relative(output / "reference-definition.json"))
    if freeze_hash:
        record["parameter_freeze_sha256"] = freeze_hash
    path = folder / "record.json"
    write_json(path, record)
    return relative(path)


def run_experiment(output, backend):
    started = time.perf_counter()
    if (output / "simulation-report.json").exists() or (output / "runs").exists():
        raise ValueError("refusing to overwrite an executed experiment")
    backend_manifest = validate_backend(output, backend)
    specification = read(output / "experiment.json")
    source_files = {p for name in ("schemas/dag", "vidur-alibabacloud/vidur", "scripts/dag_phase1",
                                 "scripts/dag_phase4", "scripts/dag_phase5", "scripts/dag_phase8")
                    for p in (ROOT / name).rglob("*") if p.is_file()
                    and p.suffix in (".py", ".json", ".sh", ".txt") and "__pycache__" not in p.parts}
    source_hashes = hashes(ROOT, source_files)
    source_identity = sha256(json.dumps(source_hashes, sort_keys=True).encode()).hexdigest()
    write_json(output / "source-identity.json", dict(runtime_sha256=source_identity, source_sha256=source_hashes))
    reference = dict(scope=specification["scope"], specification=specification,
                     backend_manifest=relative(backend / "backend-manifest.json"),
                     backend_manifest_sha256=digest(backend / "backend-manifest.json"),
                     experiment_freeze_sha256=digest(output / "experiment-freeze.json"),
                     hardware_accuracy_claim=False)
    write_json(output / "reference-definition.json", reference)
    base = output / "base-cost.json"
    write_json(base, dict(compute_profile_sha256=hashes(output / "profiles", set((output / "profiles").glob("*"))),
                          pricing=ANALYTICAL_PRICING, topology_sha256=digest(output / "inputs" / TOPOLOGY),
                          config_sha256=digest(output / "inputs/SimAI.conf"), calibration=None,
                          backend_binaries_sha256=backend_manifest["binaries_sha256"]))
    calibration = output / "calibration.json"
    freeze = output / "parameter-freeze.json"
    samples, rows = [], []
    for sample in specification["samples"]:
        name = sample["id"]
        print(f"Running {sample['split']}: {name}", flush=True)
        predictions = {role: run_prediction(output, backend, sample, role) for role in ("reference", "old", "same_cost")}
        if not math.isclose(predictions["old"]["e2e_s"], predictions["same_cost"]["e2e_s"], rel_tol=1e-10, abs_tol=1e-12):
            raise ValueError("same-cost DAG changed this serial scenario")
        records = {role + "_record": write_record(output, sample, role, prediction,
                   digest(output / "reference-definition.json") if role == "reference" else digest(base))
                   for role, prediction in predictions.items()}
        if sample["split"] == "calibration":
            offset = max(0, (predictions["reference"]["e2e_s"] - predictions["old"]["e2e_s"]) /
                         predictions["same_cost"]["tp_task_count"])
            write_json(calibration, dict(tp_cost_calibration=dict(model=specification["model"], tp=8, pp=1,
                offset_s=offset, evidence=records["reference_record"],
                topology_sha256=digest(output / "inputs" / TOPOLOGY), config_sha256=digest(output / "inputs/SimAI.conf"),
                analytical_pricing=ANALYTICAL_PRICING)))
            write_json(output / "revised-cost.json", dict(base_cost_sha256=digest(base), calibration_sha256=digest(calibration)))
            scope = {key: read(ROOT / records["reference_record"])[key] for key in ("model", "hardware", "tp", "pp", "ep", "dtype")}
            # Freeze parameters and validation request identities before running
            # any validation request. Raw model runs are inputs, never fit targets.
            input_hashes = []
            for held_out in specification["samples"]:
                if held_out["split"] == "validation":
                    path = output / (held_out["id"] + "-input.csv")
                    write_csv(path, [dict(arrived_at=0, num_prefill_tokens=held_out["prefill_tokens"],
                                          num_decode_tokens=held_out["decode_tokens"])])
                    input_hashes.append(digest(path))
            write_json(freeze, dict(calibration_group_ids=["dense_tp8_" + name],
                calibration_reference_sha256=[digest(ROOT / records["reference_record"])],
                validation_input_sha256=input_hashes,
                scenarios=dict(dense=dict(scope=scope, cost_config_sha256=digest(output / "revised-cost.json"))),
                calibration_sha256=digest(calibration), reference_definition_sha256=digest(output / "reference-definition.json"),
                validation_scope="held-out request inputs and Prefill payloads; shared fixed Decode communication cost"))
            frozen_hash = digest(freeze)
        if digest(freeze) != frozen_hash or digest(calibration) != read(freeze)["calibration_sha256"]:
            raise ValueError("calibration changed after freezing")
        revised = run_prediction(output, backend, sample, "revised_cost", calibration)
        records["revised_cost_record"] = write_record(output, sample, "revised_cost", revised,
                                                       digest(output / "revised-cost.json"), frozen_hash)
        samples.append(dict(pair_id="dense_ns3_" + name, group_id="dense_tp8_" + name, split=sample["split"], scenario="dense",
                            attribution="Fixed per-collective offset fitted only on calibration request; same-cost timing unchanged", **records))
        row = dict(sample=name, split=sample["split"], prefill_tokens=sample["prefill_tokens"], decode_tokens=sample["decode_tokens"],
                   reference_s=predictions["reference"]["e2e_s"], old_s=predictions["old"]["e2e_s"],
                   same_cost_s=predictions["same_cost"]["e2e_s"], revised_cost_s=revised["e2e_s"])
        for role in ("old", "same_cost", "revised_cost"):
            row[role + "_relative_error"] = abs(row[role + "_s"] - row["reference_s"]) / row["reference_s"]
        for role, prediction in dict(predictions, revised_cost=revised).items():
            row[role + "_ttft_s"] = prediction["ttft_s"]
            row[role + "_tpot_s"] = prediction["tpot_s"]
        rows.append(row)
    dataset = output / "validation.json"
    write_json(dataset, dict(schema_version="1.0", primary_metric="request_e2e", reference_nature="simulated",
                            required_scenarios=["dense"], parameter_freeze=dict(path=relative(freeze), sha256=frozen_hash), samples=samples))
    result = evaluate(output / "accuracy", dataset)
    validate_backend(output, backend)
    if digest(calibration) != read(freeze)["calibration_sha256"]:
        raise ValueError("calibration changed during final validation")
    if hashes(ROOT, source_files) != source_hashes:
        raise ValueError("tested source changed during the experiment")
    write_csv(output / "request-comparison.csv", rows)
    report = dict(status=result["status"], scope=specification["scope"], reference_nature="simulated",
        hardware_accuracy_claim=False, compute_accuracy_validated=False, scheduler_accuracy_validated=False,
        pd_moe_accuracy_validated=False, overall_project_acceptance="pending",
        calibration_samples=1, validation_samples=result["validation_samples"],
        old_mean_relative_error=result["old_mean_relative_error"], same_cost_mean_relative_error=result["same_cost_mean_relative_error"],
        revised_mean_relative_error=result["revised_mean_relative_error"],
        outcomes=result["outcomes"], offset_per_collective_s=read(calibration)["tp_cost_calibration"]["offset_s"],
        validation_dataset=relative(dataset), limitations=specification["limitations"], wall_time_s=time.perf_counter() - started)
    write_json(output / "simulation-report.json", report)
    git = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    write_json(output / "run-manifest.json", dict(command=[sys.executable, *sys.argv], git_head=git.stdout.strip(),
        environment=dict(python=sys.version, executable=sys.executable, prefix=sys.prefix,
                         dependencies={d.metadata["Name"]: d.version for d in importlib.metadata.distributions()}),
        source_sha256=source_hashes, frozen_parameter_sha256=frozen_hash,
        artifact_sha256=hashes(output, {p for p in output.rglob("*") if p.is_file()})))
    print(json.dumps(report, indent=2), flush=True)
    return 0 if result["status"] == "passed" else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--prepare", action="store_true")
    action.add_argument("--backend-evidence", type=Path)
    args = parser.parse_args()
    output = (ROOT / args.output).resolve()
    if output == ROOT / "results/dag/phase8" or not output.is_relative_to(ROOT / "results/dag/phase8"):
        parser.error("output must be a new directory below results/dag/phase8")
    if args.prepare:
        prepare_experiment(output)
        return 0
    backend = (ROOT / args.backend_evidence).resolve()
    if not backend.is_relative_to(output):
        parser.error("backend evidence must be inside the experiment output")
    return run_experiment(output, backend)


if __name__ == "__main__":
    raise SystemExit(main())
