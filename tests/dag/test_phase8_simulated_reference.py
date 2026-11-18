"""Check evidence admission and raw-output replay without requiring Linux/GPU."""
import json

import pytest

from scripts.dag_phase4.main import write_json
from scripts.dag_phase8.simulated_reference import seed_cache, validate_backend
from scripts.dag_phase8.accuracy import digest


def model_evidence(folder):
    inputs = folder / "inputs"
    inputs.mkdir()
    (inputs / "request.txt").write_text("frozen request")
    write_json(inputs / "frozen-inputs.json", dict(payload_bytes=dict(decode=65536)))
    write_json(folder / "experiment-freeze.json", dict(input_sha256={
        "inputs/request.txt": digest(inputs / "request.txt"),
        "inputs/frozen-inputs.json": digest(inputs / "frozen-inputs.json")}))
    backend = folder / "backend-reference"
    entries = []
    for kind in ("analytical", "ns3"):
        case = backend / "decode" / kind
        case.mkdir(parents=True)
        (case / "raw.csv").write_text("layer_name,a,b,c,d,fwd exposed comm,g,h,fwd total comm\nlayer0,0,0,0,0,85.745,0,0,85.745\n")
        write_json(case / "collective.json", dict(csv="raw.csv", unit="us", values=[85.745]))
        entries.append(dict(case="decode", backend=kind, payload_bytes=65536,
                            collective_sha256=digest(case / "collective.json")))
    write_json(backend / "backend-manifest.json", dict(fresh_execution=True,
        frozen_inputs_sha256=digest(inputs / "frozen-inputs.json"), records=entries,
        artifact_sha256={p.relative_to(backend).as_posix(): digest(p) for p in backend.rglob("*") if p.is_file()}))
    return backend


@pytest.mark.parametrize("mutation", ["request", "csv", "payload", "unit", "missing"])
def test_changed_or_incomplete_model_evidence_is_rejected(tmp_path, mutation):
    backend = model_evidence(tmp_path)
    assert validate_backend(tmp_path, backend)["fresh_execution"]
    if mutation == "request":
        (tmp_path / "inputs/request.txt").write_text("changed request")
    elif mutation == "csv":
        (backend / "decode/ns3/raw.csv").write_text("layer_name,fwd total comm\nlayer0,1\n")
    else:
        path = backend / "backend-manifest.json"
        manifest = json.loads(path.read_text())
        if mutation == "payload":
            manifest["records"][0]["payload_bytes"] = 1
        elif mutation == "missing":
            manifest["records"].pop()
        else:
            record = backend / "decode/ns3/collective.json"
            write_json(record, dict(csv="raw.csv", unit="s", values=[85.745]))
            manifest["artifact_sha256"]["decode/ns3/collective.json"] = digest(record)
            manifest["records"][1]["collective_sha256"] = digest(record)
        write_json(path, manifest)
    with pytest.raises(ValueError):
        validate_backend(tmp_path, backend)


@pytest.mark.parametrize("kind", ["ns3", "analytical"])
@pytest.mark.parametrize("rounded_tokens", [8, 8.0])
def test_replay_preserves_raw_bytes_and_uses_original_predictor_key(tmp_path, monkeypatch, kind, rounded_tokens):
    from vidur.execution_time_predictor.communication_time_predictor import TPTimePredictor
    from types import SimpleNamespace
    import scripts.dag_phase8.simulated_reference as experiment
    monkeypatch.setattr(experiment, "ROOT", tmp_path)
    backend = model_evidence(tmp_path)
    # Seed the exact same paths consumed by the actual original predictor.
    inputs = tmp_path / "inputs"
    (inputs / experiment.TOPOLOGY).write_text("logical topology")
    (inputs / "SimAI.conf").write_text("logical configuration")
    cache = tmp_path / "cli-cache"
    seed_cache(tmp_path, backend, cache, kind)
    predictor = TPTimePredictor(SimpleNamespace(num_layers=32, embedding_dim=4096),
        SimpleNamespace(num_pipeline_stages=1, tensor_parallel_size=8, world_size=8),
        SimpleNamespace(simai_dir=str(cache), simai_simulation_topo=str(inputs / experiment.TOPOLOGY),
                        simai_simulation_config=str(inputs / "SimAI.conf"),
                        simai_analytical_nvlink_gbps=300.0, simai_analytical_nic_gbps=25.0,
                        simai_analytical_nics_per_server=8,
                        nccl_cpu_launch_overhead_ms=0, nccl_cpu_skew_overhead_per_device_ms=0))
    method = predictor.get_execution_time if kind == "ns3" else predictor.get_execution_time_by_simai_analytical
    assert method(SimpleNamespace(_total_num_tokens_rounded=rounded_tokens)) == pytest.approx(.085745)
    replayed = list(cache.glob("*EndToEnd_*.csv"))
    assert len(replayed) == 2
    assert all(p.read_bytes() == (backend / f"decode/{kind}/raw.csv").read_bytes() for p in replayed)


def test_experiment_holds_out_prefill_payloads_and_declares_shared_decode():
    from scripts.dag_phase8.simulated_reference import EXPERIMENT
    spec = json.loads(EXPERIMENT.read_text())
    calibration = [s for s in spec["samples"] if s["split"] == "calibration"]
    validation = [s for s in spec["samples"] if s["split"] == "validation"]
    assert len(calibration) == 1 and len(validation) == 3
    assert not {s["prefill_tokens"] for s in calibration}.intersection(s["prefill_tokens"] for s in validation)
    assert any("share the Decode" in limit for limit in spec["limitations"])
