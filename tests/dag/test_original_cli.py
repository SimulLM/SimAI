"""Regressions for the original CLI's flattened configuration parser."""
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
