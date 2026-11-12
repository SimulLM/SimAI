"""WSL replay of the frozen H20 TP8 collective workloads."""
import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
SIZES = {"calibration": 16 * 1024**2, "validation": 64 * 1024**2}
TOPOLOGY = "Rail_Opti_SingleToR_8g_8gps_200Gbps_H20"
ANALYTICAL_PRICING = {
    "simai_analytical_nvlink_gbps": 300.0,
    "simai_analytical_nic_gbps": 25.0,
    "simai_analytical_nics_per_server": 8,
}
ANALYTICAL_FLAGS = {
    "-nv": ANALYTICAL_PRICING["simai_analytical_nvlink_gbps"],
    "-nic": ANALYTICAL_PRICING["simai_analytical_nic_gbps"],
    "-n_p_s": ANALYTICAL_PRICING["simai_analytical_nics_per_server"],
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_json(path, data):
    path.write_text(json.dumps(data, allow_nan=False, indent=2) + "\n", encoding="utf-8")


def prepare(output, sizes=None):
    sizes = SIZES if sizes is None else sizes
    output.mkdir(parents=True, exist_ok=False)
    original = ROOT / "example/microAllReduce.txt"
    shutil.copyfile(original, output / "smoke.txt")
    header = original.read_text(encoding="utf-8").splitlines()[0].replace("vpp: 8", "vpp: 32") + " pp_comm: 0"
    for split, payload in sizes.items():
        (output / f"{split}.txt").write_text(
            f"{header}\n1\nlayer0 -1 1 ALLREDUCE {payload} 0 NONE 0 0 NONE 0 100\n", encoding="utf-8")
    generator = ROOT / "astra-sim-alibabacloud/inputs/topo/gen_Topo_Template.py"
    import sys
    command = [sys.executable, str(generator), "--ro", "-g", "8", "-gt", "H20",
               "-bw", "200Gbps", "-nvbw", "2400Gbps"]
    subprocess.run(command, cwd=output, check=True)
    conf = ROOT / "astra-sim-alibabacloud/inputs/config/SimAI.conf"
    # Keep every simulator output local to its individual run directory.
    configuration = re.sub(r"/etc/astra-sim/simulation/([^\s]+)", r"\1", conf.read_text(encoding="utf-8"))
    (output / "SimAI.conf").write_text(configuration, encoding="utf-8")
    save_json(output / "frozen-inputs.json", {
        "topology_command": command, "dtype": "fp16", "rank_group": list(range(8)), "payload_bytes": sizes,
        "analytical_model": {"nvlink_GBps": 300, "nic_GBps": 25, "gpus_per_server": 8},
        "analytical_pricing": ANALYTICAL_PRICING,
        "sha256": {p.name: digest(p) for p in output.iterdir() if p.is_file()},
    })


def collective_times(path):
    """Read the per-layer forward collective field in microseconds."""
    with path.open(encoding="utf-8", newline="") as stream:
        rows = iter(csv.reader(stream))
        for header in rows:
            if header and header[0].strip() == "layer_name":
                index = [field.strip() for field in header].index("fwd total comm")
                break
        else:
            raise ValueError(f"missing per-layer collective header: {path}")
        times = []
        for row in rows:
            if not row or row[0].strip() in {"SUM", "total exposed comm"}:
                break
            latency = float(row[index])
            if not math.isfinite(latency) or latency <= 0:
                raise ValueError(f"invalid forward collective latency: {latency}")
            times.append(latency)
    return times


def run(inputs, binaries, backend, case, output):
    output.mkdir(parents=True, exist_ok=False)
    frozen = json.loads((inputs / "frozen-inputs.json").read_text(encoding="utf-8"))
    for name, expected in frozen["sha256"].items():
        if digest(inputs / name) != expected:
            raise ValueError(f"frozen input changed: {name}")
    workload = inputs / f"{case}.txt"
    env = dict(os.environ, AS_SEND_LAT="3" if case == "smoke" else "6", AS_NVLS_ENABLE="1")
    if backend == "ns3":
        executable = binaries / "SimAI_simulator"
        command = [str(executable), "-t", "8", "-w", str(workload),
                   "-n", str(inputs / TOPOLOGY), "-c", str(inputs / "SimAI.conf")]
        result_file = output / "ncclFlowModel_EndToEnd.csv"
    else:
        executable = binaries / "SimAI_analytical"
        (output / "results").mkdir()
        ratio = output / "astra-sim-alibabacloud/inputs/ratio"
        shutil.copytree(ROOT / "astra-sim-alibabacloud/inputs/ratio", ratio)
        command = [str(executable), "-w", str(workload), "-g", "8", "-g_p_s", "8", "-r", "collective-"]
        for flag, value in ANALYTICAL_FLAGS.items():
            command.extend((flag, str(value)))
        result_file = output / "results/collective-EndToEnd.csv"
    save_json(output / "command.json", {"argv": command, "binary_sha256": digest(executable),
                                      "environment": {key: env[key] for key in ("AS_SEND_LAT", "AS_NVLS_ENABLE")}})
    started = time.perf_counter()
    with (output / "process.log").open("w", encoding="utf-8") as log:
        process = subprocess.run(command, env=env, cwd=output, stdout=log, stderr=subprocess.STDOUT, timeout=300)
    save_json(output / "process-result.json", {"exit_code": process.returncode,
                                             "wall_time_s": time.perf_counter() - started})
    process.check_returncode()
    expected = 2 if case == "smoke" else 1
    if backend == "ns3":
        log = (output / "process.log").read_text(encoding="utf-8", errors="replace")
        for counter in ("injected", "finished"):
            if not re.search(rf"Total streams {counter}: {expected}\b", log):
                raise ValueError(f"missing expected ns-3 stream count: {counter}={expected}")
    times = collective_times(result_file)
    if len(times) != expected:
        raise ValueError(f"expected {expected} collective rows, found {len(times)}")
    save_json(output / "collective.json", {"case": case, "backend": backend, "nature": "simulated",
                                         "csv": result_file.relative_to(output).as_posix(),
                                         "column": "fwd total comm", "unit": "us", "values": times})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", type=Path)
    parser.add_argument("--binaries", type=Path)
    parser.add_argument("--backend", choices=("analytical", "ns3"))
    parser.add_argument("--case", choices=("smoke", *SIZES))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.backend:
        run(args.inputs.resolve(), args.binaries.resolve(), args.backend, args.case, args.output.resolve())
    else:
        prepare(args.inputs.resolve())


if __name__ == "__main__":
    main()
