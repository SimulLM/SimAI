"""Build a phase-aware Vidur profile from vLLM diagnostic summaries.

The input files are raw eligible samples produced by the archived diagnostic
scripts.  This tool never reads request completion times, so the resulting
profile is independent of calibration and validation.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
from collections import defaultdict
from pathlib import Path

from scripts.dag_defense.profile_mapping_contract import MappingContract, merge_rope_into_pre_proj


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def median(values: list[float]) -> float:
    return statistics.median(values) if values else 0.0


def write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(compute_path: Path, attention_path: Path, cpu_path: Path, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    compute = read_csv(compute_path)
    attention = read_csv(attention_path)
    cpu = read_csv(cpu_path)
    contract = MappingContract()

    compute_groups: dict[tuple[str, int, int], dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in compute:
        if row.get("eligible") != "1":
            continue
        key = (row["phase"], int(row["input_tokens"]), int(row["actual_batch"]))
        group = compute_groups[key]
        for name in (
            "attn_pre_proj",
            "attn_rope",
            "attn_post_proj",
            "mlp_up_proj",
            "mlp_act",
            "mlp_down_proj",
            "input_layernorm",
            "post_attention_layernorm",
        ):
            group[name].append(float(row[name]))

    compute_fields = [
        "n_head",
        "n_kv_head",
        "n_embd",
        "n_expanded_embd",
        "use_gated_mlp",
        "vocab_size",
        "num_tensor_parallel_workers",
        "num_tokens",
        "time_stats.attn_pre_proj.median",
        "time_stats.attn_post_proj.median",
        "time_stats.mlp_up_proj.median",
        "time_stats.mlp_down_proj.median",
        "time_stats.mlp_act.median",
        "time_stats.input_layernorm.median",
        "time_stats.post_attention_layernorm.median",
        "time_stats.attn_rope.median",
        "time_stats.add.median",
    ]
    compute_rows: list[dict[str, object]] = []
    for (phase, input_tokens, batch), group in sorted(compute_groups.items()):
        pre, rope = merge_rope_into_pre_proj(
            median(group["attn_pre_proj"]), median(group["attn_rope"])
        )
        tokens = input_tokens * batch if phase == "prefill" else batch
        compute_rows.append(
            {
                "n_head": 32,
                "n_kv_head": 32,
                "n_embd": 4096,
                "n_expanded_embd": 11008,
                "use_gated_mlp": True,
                "vocab_size": 32000,
                "num_tensor_parallel_workers": 1,
                "num_tokens": tokens,
                "time_stats.attn_pre_proj.median": pre,
                "time_stats.attn_post_proj.median": median(group["attn_post_proj"]),
                "time_stats.mlp_up_proj.median": median(group["mlp_up_proj"]),
                "time_stats.mlp_down_proj.median": median(group["mlp_down_proj"]),
                "time_stats.mlp_act.median": median(group["mlp_act"]),
                "time_stats.input_layernorm.median": median(group["input_layernorm"]),
                "time_stats.post_attention_layernorm.median": median(group["post_attention_layernorm"]),
                # The predictor schema has a separate field, but the contract
                # intentionally folds it into pre-projection to avoid a second
                # count in both baseline and DAG.
                "time_stats.attn_rope.median": rope,
                "time_stats.add.median": 0.0,
            }
        )

    attention_groups: dict[tuple[str, int, int], list[float]] = defaultdict(list)
    for row in attention:
        if row.get("eligible") == "1":
            attention_groups[(row["phase"], int(row["input_tokens"]), int(row["actual_batch"]))].append(
                float(row["attention_combined"])
            )
    attention_fields = [
        "n_embd",
        "n_q_head",
        "n_kv_head",
        "block_size",
        "num_tensor_parallel_workers",
        "batch_size",
        "prefill_chunk_size",
        "kv_cache_size",
        "time_stats.attn_kv_cache_save.median",
        "time_stats.attn_prefill.median",
        "time_stats.attn_decode.median",
    ]
    attention_rows: list[dict[str, object]] = []
    for (phase, input_tokens, batch), values in sorted(attention_groups.items()):
        attention_rows.append(
            {
                "n_embd": 4096,
                "n_q_head": 32,
                "n_kv_head": 32,
                "block_size": 16,
                "num_tensor_parallel_workers": 1,
                "batch_size": batch,
                "prefill_chunk_size": input_tokens if phase == "prefill" else 0,
                "kv_cache_size": 0 if phase == "prefill" else input_tokens,
                "time_stats.attn_kv_cache_save.median": 0.0,
                "time_stats.attn_prefill.median": median(values) if phase == "prefill" else 0.0,
                "time_stats.attn_decode.median": median(values) if phase == "decode" else 0.0,
            }
        )

    cpu_groups: dict[tuple[str, int, int], dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in cpu:
        if row.get("eligible") == "1":
            key = (row["phase"], int(row["input_tokens"]), int(row["actual_batch"]))
            cpu_groups[key][row["event"]].append(float(row["duration_ns"]) / 1e6)
    cpu_fields = [
        "model_name",
        "tensor_parallel_degree",
        "phase",
        "input_tokens",
        "batch_size",
        "schedule_median",
        "sampler_e2e_median",
        "prepare_inputs_e2e_median",
        "process_model_outputs_median",
        "ray_comm_time_mean",
    ]
    cpu_rows: list[dict[str, object]] = []
    for (phase, input_tokens, batch), group in sorted(cpu_groups.items()):
        cpu_rows.append(
            {
                "model_name": "NousResearch/Llama-2-7b-hf",
                "tensor_parallel_degree": 1,
                "phase": phase,
                "input_tokens": input_tokens,
                "batch_size": batch,
                "schedule_median": median(group["schedule"]),
                "sampler_e2e_median": median(group["sampler_host_call"]),
                "prepare_inputs_e2e_median": median(group["prepare_inputs"]),
                "process_model_outputs_median": median(group["process_model_outputs"]),
                "ray_comm_time_mean": 0.0,
            }
        )

    network_fields = [
        "collective",
        "num_workers",
        "devices_per_node",
        "size",
        "time_stats.send_recv.median",
        "time_stats.all_reduce.median",
    ]
    network_rows = [
        {
            "collective": "send_recv",
            "num_workers": 1,
            "devices_per_node": 2,
            "size": 1,
            "time_stats.send_recv.median": 0.0,
            "time_stats.all_reduce.median": 0.0,
        }
    ]

    write_csv(output / "compute.csv", compute_fields, compute_rows)
    write_csv(output / "attention.csv", attention_fields, attention_rows)
    write_csv(output / "cpu.csv", cpu_fields, cpu_rows)
    write_csv(output / "network.csv", network_fields, network_rows)
    files = {name: sha256(output / name) for name in ("compute.csv", "attention.csv", "cpu.csv", "network.csv")}
    manifest = {
        "status": "candidate_hardware_profile",
        "model": "NousResearch/Llama-2-7b-hf",
        "revision": "8efe6c9b93655b934e27bd9981e3ec13e55aee9d",
        "dtype": "float16",
        "hardware": "NVIDIA H800 PCIe; GPU0/GPU1; TP1",
        "mapping_contract": contract.as_dict(),
        "source_files": [str(compute_path), str(attention_path), str(cpu_path)],
        "source_sha256": {str(p): sha256(p) for p in (compute_path, attention_path, cpu_path)},
        "files": files,
        "coverage": {
            "compute_rows": len(compute_rows),
            "attention_rows": len(attention_rows),
            "cpu_rows": len(cpu_rows),
        },
        "limitations": [
            "diagnostic CUDA-event synchronization perturbs timing",
            "combined attention includes FlashAttention/KV work; cache-save is zero to avoid double count",
            "sampler_host_call is an inclusive boundary bucket and is not pure CPU time",
            "router/frontend/IPC and non-KV PD payloads are outside this profile",
        ],
    }
    (output / "profile-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compute-samples", type=Path, required=True)
    parser.add_argument("--attention-samples", type=Path, required=True)
    parser.add_argument("--cpu-samples", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.compute_samples, args.attention_samples, args.cpu_samples, args.output), indent=2))


if __name__ == "__main__":
    main()
