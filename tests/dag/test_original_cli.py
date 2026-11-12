"""Regressions for the original CLI's flattened configuration parser."""
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from vidur.config import SimulationConfig
from vidur.config.flat_dataclass import create_flat_dataclass


def test_original_cli_help():
    root = Path(__file__).resolve().parents[2]
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(root / "vidur-alibabacloud"), str(root), env.get("PYTHONPATH", "")])
    result = subprocess.run([sys.executable, "-m", "vidur.main", "--help"],
                            cwd=root, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "--execution_mode" in result.stdout
    assert "--no-metrics_config_enable_chrome_trace" in result.stdout


@pytest.mark.parametrize("mode", ["legacy", "dag_coarse"])
@pytest.mark.parametrize("enabled", [True, False])
def test_original_cli_switches_and_type_conversion(monkeypatch, mode, enabled):
    switch = "--metrics_config_enable_chrome_trace" if enabled else "--no-metrics_config_enable_chrome_trace"
    monkeypatch.setattr(sys, "argv", ["vidur.main", switch, "--execution_mode", mode,
                                     "--seed", "17"])
    config = create_flat_dataclass(SimulationConfig).create_from_cli_args()
    assert config.metrics_config_enable_chrome_trace is enabled
    assert config.execution_mode == mode
    assert config.seed == 17 and type(config.seed) is int


def test_original_cli_defaults(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["vidur.main"])
    config = create_flat_dataclass(SimulationConfig).create_from_cli_args()
    assert config.execution_mode == "legacy"


@pytest.mark.parametrize(("changed", "value"), [
    ("simai_analytical_nvlink_gbps", 600),
    ("simai_analytical_nic_gbps", 50),
    ("simai_analytical_nics_per_server", 4),
    (None, None),
])
def test_original_cli_rejects_incompatible_tp_calibration(tmp_path, changed, value):
    pricing = {
        "simai_analytical_nvlink_gbps": 300,
        "simai_analytical_nic_gbps": 25,
        "simai_analytical_nics_per_server": 8,
    }
    topo = tmp_path / "topology"
    conf = tmp_path / "SimAI.conf"
    topo.write_text("frozen topology", encoding="utf-8")
    conf.write_text("frozen SimAI config", encoding="utf-8")
    calibration = {
        "model": "meta-llama/Llama-2-7b-hf", "tp": 8, "pp": 1,
        "offset_s": 92.563e-6, "evidence": "regression fixture",
        "topology_sha256": sha256(topo.read_bytes()).hexdigest(),
        "config_sha256": sha256(conf.read_bytes()).hexdigest(),
    }
    current = dict(pricing)
    if changed:
        calibration["analytical_pricing"] = pricing
        current[changed] = value
    path = tmp_path / "calibration.json"
    path.write_text(json.dumps({"tp_cost_calibration": calibration}), encoding="utf-8")
    root = Path(__file__).resolve().parents[2]
    env = dict(os.environ, WANDB_MODE="disabled")
    env["PYTHONPATH"] = os.pathsep.join(
        [str(root / "vidur-alibabacloud"), str(root), env.get("PYTHONPATH", "")])
    prefix = "--random_forrest_execution_time_predictor_config_"
    backend_dir = tmp_path / "backend"
    command = [sys.executable, "-m", "vidur.main", "--execution_mode", "dag_expanded",
               "--dag_resource_config", str(path), "--metrics_config_output_dir", str(tmp_path / "metrics"),
               "--replica_config_model_name", calibration["model"], "--replica_config_tensor_parallel_size", "8",
               prefix + "backend", "simai_analytical", prefix + "simai_dir", str(backend_dir),
               prefix + "simai_simulation_topo", str(topo), prefix + "simai_simulation_config", str(conf)]
    for key, setting in current.items():
        command.extend((prefix + key, str(setting)))
    result = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode != 0
    expected = f"TP calibration does not match {changed}" if changed else "requires frozen analytical_pricing"
    assert expected in result.stderr, result.stdout + result.stderr
    assert not backend_dir.exists()
