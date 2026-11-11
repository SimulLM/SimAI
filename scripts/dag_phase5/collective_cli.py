"""Execute and verify real Vidur CLI collectives with isolated backend state."""
import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sys

from collective import ROOT, SIZES, TOPOLOGY, collective_times, digest, save_json

sys.path.insert(0, str(ROOT))
from scripts.dag_phase4.main import cli_command, run_cli, synthetic_profiles, write_csv

MODEL = "meta-llama/Llama-2-7b-hf"
PREFIX = "--random_forrest_execution_time_predictor_config_"


def option(command, name, value):
    if name in command:
        command[command.index(name) + 1] = str(value)
    else:
        command.extend((name, str(value)))


def run(inputs, binaries, case, backend, mode, output, calibration=None):
    output.mkdir(parents=True, exist_ok=False)
    backend_dir = output / "backend"
    (backend_dir / "bin").mkdir(parents=True)
    (backend_dir / "results").mkdir()
    binary = "SimAI_analytical" if backend == "simai_analytical" else "SimAI_simulator"
    # An absolute symlink retains ns-3's build-directory runtime dependencies.
    (backend_dir / "bin" / binary).symlink_to(binaries / binary)
    shutil.copytree(ROOT / "astra-sim-alibabacloud/inputs/ratio",
                    backend_dir / "astra-sim-alibabacloud/inputs/ratio")
    profiles = output / "synthetic-profiles"
    synthetic_profiles(profiles, tp_sizes=(8,), network_devices=8)
    trace = output / "requests.csv"
    payload = json.loads((inputs / "frozen-inputs.json").read_text(encoding="utf-8"))["payload_bytes"][case]
    tokens = payload // (4096 * 2)
    write_csv(trace, [dict(arrived_at=0, num_prefill_tokens=tokens, num_decode_tokens=2)])
    destination = output / mode
    command = cli_command(mode, destination, profiles, trace, tp=8)
    for key, value in {
        "--replica_config_device": "h20",
        "--replica_config_network_device": "h20_dgx",
        "--trace_request_generator_config_max_tokens": tokens + 16,
        "--sarathi_scheduler_config_chunk_size": tokens,
        "--sarathi_scheduler_config_batch_size_cap": 1,
        PREFIX + "prediction_max_batch_size": 1,
        PREFIX + "prediction_max_tokens_per_request": 2 * tokens,
        PREFIX + "prediction_max_prefill_chunk_size": tokens,
        PREFIX + "kv_cache_prediction_granularity": tokens,
        PREFIX + "backend": backend,
        PREFIX + "simai_dir": backend_dir,
        PREFIX + "simai_simulation_topo": inputs / TOPOLOGY,
        PREFIX + "simai_simulation_config": inputs / "SimAI.conf",
        PREFIX + "simai_analytical_nvlink_gbps": 300,
        PREFIX + "simai_analytical_nic_gbps": 25,
        PREFIX + "simai_analytical_nics_per_server": 8,
        PREFIX + "nccl_cpu_launch_overhead_ms": 0,
        PREFIX + "nccl_cpu_skew_overhead_per_device_ms": 0,
    }.items():
        option(command, key, value)
    if calibration:
        option(command, "--dag_resource_config", calibration)
    # Match the direct replay's collective algorithm configuration.
    command = ["env", "AS_SEND_LAT=6", "AS_NVLS_ENABLE=1", *command] if os.name == "posix" else command
    summary, native = run_cli(command, destination)
    if summary["status"] != "completed" or not all(r["completed"] for r in summary["requests"]):
        raise ValueError("Vidur did not finish the collective workload")
    generated = [p for p in (backend_dir / "tmp_simai_inference_workload").glob("*.txt")
                 if f"ALLREDUCE {payload} " in p.read_text(encoding="utf-8")]
    if len(generated) != 1:
        raise ValueError("Vidur did not run a unique matching collective workload")
    expected = (inputs / f"{case}.txt").read_text(encoding="utf-8").splitlines()
    actual = generated[0].read_text(encoding="utf-8").splitlines()
    if actual != expected:
        raise ValueError("Vidur collective row differs from the frozen input")
    stem = "analytical_EndToEnd_" if backend == "simai_analytical" else "ncclFlowModel_EndToEnd_"
    key = f"{generated[0].stem.removeprefix('allreduce_')}_{inputs / TOPOLOGY}_{inputs / 'SimAI.conf'}"
    if backend == "simai_analytical":
        key += f"_8_{ {'-nv': 300.0, '-nic': 25.0, '-n_p_s': 8} }"
    backend_result = backend_dir / (stem + hashlib.md5(key.encode()).hexdigest() + ".csv")
    [backend_us] = collective_times(backend_result)
    value = backend_us * 1e-6
    timeline = native / "timeline.csv"
    if mode == "dag_expanded":
        with timeline.open(encoding="utf-8", newline="") as stream:
            matches = [r for r in csv.DictReader(stream) if r["task_id"] == "layer0.attention.tp"]
        task = matches[0]
        value = float(task["end_at_s"]) - float(task["start_at_s"])
        parameters = json.loads(calibration.read_text(encoding="utf-8"))["tp_cost_calibration"] if calibration else {}
        expected_s = backend_us * 1e-6 * parameters.get("scale", 1)
        expected_s += parameters.get("offset_s", 0)
        if not math.isclose(value, expected_s, rel_tol=1e-9, abs_tol=1e-12):
            raise ValueError("DAG TP service differs from the backend collective price")
    save_json(output / "collective.json", {
        "case": case, "backend": backend, "mode": mode, "latency_s": value, "backend_us": backend_us,
        "binary_sha256": digest(binaries / binary),
        "workload": generated[0].relative_to(output).as_posix(),
        "backend_csv": backend_result.relative_to(output).as_posix(),
        "native": native.relative_to(output).as_posix(),
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for path in ("inputs", "binaries", "output"):
        parser.add_argument(path, type=lambda value: Path(value).resolve())
    parser.add_argument("--case", choices=SIZES, required=True)
    parser.add_argument("--backend", choices=("simai_analytical", "simai_simulation"), required=True)
    parser.add_argument("--mode", choices=("legacy", "dag_expanded"), required=True)
    parser.add_argument("--calibration", type=lambda value: Path(value).resolve())
    run(**vars(parser.parse_args()))
