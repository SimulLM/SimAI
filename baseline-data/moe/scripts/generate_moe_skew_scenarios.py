#!/usr/bin/env python3
"""Generate deterministic uniform, hotspot, and long-tail MoE load matrices."""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
import sys
from pathlib import Path
from typing import Iterable


def allocate_integer_total(probabilities: list[float], total: int) -> list[int]:
    raw = [probability * total for probability in probabilities]
    counts = [math.floor(value) for value in raw]
    remainder = total - sum(counts)
    order = sorted(
        range(len(raw)),
        key=lambda index: (raw[index] - counts[index], -index),
        reverse=True,
    )
    for index in order[:remainder]:
        counts[index] += 1
    return counts


def gini(values: Iterable[int]) -> float:
    ordered = sorted(values)
    total = sum(ordered)
    if not ordered or total == 0:
        return 0.0
    weighted = sum((index + 1) * value for index, value in enumerate(ordered))
    return (2 * weighted) / (len(ordered) * total) - (len(ordered) + 1) / len(ordered)


def normalized_entropy(values: Iterable[int]) -> float:
    values = list(values)
    total = sum(values)
    if len(values) <= 1 or total == 0:
        return 1.0
    entropy = -sum(
        (value / total) * math.log(value / total)
        for value in values
        if value > 0
    )
    return entropy / math.log(len(values))


def metrics(values: list[int]) -> dict[str, float | int]:
    mean = statistics.mean(values)
    top_count = max(1, math.ceil(len(values) * 0.10))
    ordered = sorted(values, reverse=True)
    total = sum(values)
    return {
        "total_assignments": total,
        "mean_load": round(mean, 6),
        "max_load": max(values),
        "min_load": min(values),
        "max_to_mean": round(max(values) / mean, 6) if mean else 0.0,
        "coefficient_of_variation": round(statistics.pstdev(values) / mean, 6)
        if mean
        else 0.0,
        "gini": round(gini(values), 6),
        "normalized_entropy": round(normalized_entropy(values), 6),
        "top_1_share": round(ordered[0] / total, 6) if total else 0.0,
        "top_10pct_share": round(sum(ordered[:top_count]) / total, 6)
        if total
        else 0.0,
        "active_count": sum(value > 0 for value in values),
    }


def scenario_probabilities(
    name: str,
    num_experts: int,
    seed: int,
    hotspot_fraction: float,
    hotspot_share: float,
    zipf_alpha: float,
) -> tuple[list[float], dict[str, object]]:
    if name == "uniform":
        return [1 / num_experts] * num_experts, {
            "distribution": "equal probability for every expert",
            "placement": "not applicable",
        }

    if name == "hotspot":
        hot_count = max(1, round(num_experts * hotspot_fraction))
        if hot_count >= num_experts:
            raise ValueError("hotspot_fraction must leave at least one non-hot expert")
        hot_probability = hotspot_share / hot_count
        cold_probability = (1 - hotspot_share) / (num_experts - hot_count)
        probabilities = [
            hot_probability if index < hot_count else cold_probability
            for index in range(num_experts)
        ]
        return probabilities, {
            "distribution": f"{hot_count} hot experts receive {hotspot_share:.1%} of assignments",
            "hot_expert_ids": list(range(hot_count)),
            "placement": "clustered at low expert IDs to create explicit rank hotspots",
        }

    if name == "long_tail":
        weights = [1 / (rank**zipf_alpha) for rank in range(1, num_experts + 1)]
        denominator = sum(weights)
        ranked_probabilities = [weight / denominator for weight in weights]
        expert_ids = list(range(num_experts))
        random.Random(seed).shuffle(expert_ids)
        probabilities = [0.0] * num_experts
        for probability, expert_id in zip(ranked_probabilities, expert_ids):
            probabilities[expert_id] = probability
        return probabilities, {
            "distribution": f"Zipf probabilities with alpha={zipf_alpha}",
            "rank_to_expert_permutation": expert_ids,
            "placement": f"seeded permutation with seed={seed}",
        }

    raise ValueError(f"unknown scenario: {name}")


def build_scenario(
    name: str,
    ep_size: int,
    num_experts: int,
    total_assignments: int,
    seed: int,
    hotspot_fraction: float,
    hotspot_share: float,
    zipf_alpha: float,
) -> dict[str, object]:
    if num_experts % ep_size != 0:
        raise ValueError("num_experts must be divisible by every EP size")
    probabilities, parameters = scenario_probabilities(
        name,
        num_experts,
        seed,
        hotspot_fraction,
        hotspot_share,
        zipf_alpha,
    )
    expert_loads = allocate_integer_total(probabilities, total_assignments)
    experts_per_rank = num_experts // ep_size
    rank_loads = [
        sum(expert_loads[rank * experts_per_rank : (rank + 1) * experts_per_rank])
        for rank in range(ep_size)
    ]
    if sum(expert_loads) != total_assignments or sum(rank_loads) != total_assignments:
        raise AssertionError("assignment conservation failed")

    return {
        "scenario_id": f"{name}_ep{ep_size}",
        "mode": name,
        "ep_size": ep_size,
        "experts_per_rank": experts_per_rank,
        "parameters": parameters,
        "expert_metrics": metrics(expert_loads),
        "rank_metrics": metrics(rank_loads),
        "expert_loads": [
            {
                "expert_id": expert_id,
                "rank_id": expert_id // experts_per_rank,
                "assignments": assignments,
                "share": round(assignments / total_assignments, 9),
            }
            for expert_id, assignments in enumerate(expert_loads)
        ],
        "rank_loads": [
            {
                "rank_id": rank_id,
                "assignments": assignments,
                "share": round(assignments / total_assignments, 9),
            }
            for rank_id, assignments in enumerate(rank_loads)
        ],
    }


def write_csv(path: Path, scenarios: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "scenario_id",
                "mode",
                "ep_size",
                "expert_id",
                "rank_id",
                "assignments",
                "share",
            ],
        )
        writer.writeheader()
        for scenario in scenarios:
            for expert in scenario["expert_loads"]:
                writer.writerow(
                    {
                        "scenario_id": scenario["scenario_id"],
                        "mode": scenario["mode"],
                        "ep_size": scenario["ep_size"],
                        **expert,
                    }
                )


def write_summary_csv(path: Path, scenarios: list[dict[str, object]]) -> None:
    fields = [
        "scenario_id",
        "mode",
        "ep_size",
        "total_assignments",
        "expert_max_to_mean",
        "expert_cv",
        "expert_gini",
        "expert_normalized_entropy",
        "expert_top_10pct_share",
        "rank_max_to_mean",
        "rank_cv",
        "rank_gini",
        "rank_top_10pct_share",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for scenario in scenarios:
            expert = scenario["expert_metrics"]
            rank = scenario["rank_metrics"]
            writer.writerow(
                {
                    "scenario_id": scenario["scenario_id"],
                    "mode": scenario["mode"],
                    "ep_size": scenario["ep_size"],
                    "total_assignments": expert["total_assignments"],
                    "expert_max_to_mean": expert["max_to_mean"],
                    "expert_cv": expert["coefficient_of_variation"],
                    "expert_gini": expert["gini"],
                    "expert_normalized_entropy": expert["normalized_entropy"],
                    "expert_top_10pct_share": expert["top_10pct_share"],
                    "rank_max_to_mean": rank["max_to_mean"],
                    "rank_cv": rank["coefficient_of_variation"],
                    "rank_gini": rank["gini"],
                    "rank_top_10pct_share": rank["top_10pct_share"],
                }
            )


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tokens", type=int, default=16384)
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--num-experts", type=int, default=256)
    parser.add_argument("--ep-sizes", type=int, nargs="+", default=[32, 128])
    parser.add_argument("--seed", type=int, default=20250321)
    parser.add_argument("--hotspot-fraction", type=float, default=0.10)
    parser.add_argument("--hotspot-share", type=float, default=0.50)
    parser.add_argument("--zipf-alpha", type=float, default=1.20)
    parser.add_argument(
        "--output-json",
        type=Path,
        default=repo_root / "docs" / "data" / "moe_skew_scenarios.json",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=repo_root / "docs" / "data" / "moe_skew_expert_loads.csv",
    )
    parser.add_argument(
        "--output-summary-csv",
        type=Path,
        default=repo_root / "docs" / "data" / "moe_skew_summary.csv",
    )
    args = parser.parse_args()

    if args.tokens <= 0 or args.top_k <= 0 or args.num_experts <= 1:
        parser.error("tokens, top-k, and num-experts must be positive")
    if not 0 < args.hotspot_fraction < 1:
        parser.error("hotspot-fraction must be between 0 and 1")
    if not 0 < args.hotspot_share < 1:
        parser.error("hotspot-share must be between 0 and 1")
    if args.zipf_alpha <= 0:
        parser.error("zipf-alpha must be positive")

    total_assignments = args.tokens * args.top_k
    scenarios = [
        build_scenario(
            mode,
            ep_size,
            args.num_experts,
            total_assignments,
            args.seed,
            args.hotspot_fraction,
            args.hotspot_share,
            args.zipf_alpha,
        )
        for ep_size in args.ep_sizes
        for mode in ("uniform", "hotspot", "long_tail")
    ]
    result = {
        "schema_version": 1,
        "configuration": {
            "tokens": args.tokens,
            "top_k": args.top_k,
            "total_assignments": total_assignments,
            "num_experts": args.num_experts,
            "ep_sizes": args.ep_sizes,
            "expert_to_rank_mapping": "contiguous expert IDs per rank",
            "seed": args.seed,
            "hotspot_fraction": args.hotspot_fraction,
            "hotspot_share": args.hotspot_share,
            "zipf_alpha": args.zipf_alpha,
        },
        "quality_checks": {
            "all_scenarios_conserve_assignments": all(
                scenario["expert_metrics"]["total_assignments"] == total_assignments
                and scenario["rank_metrics"]["total_assignments"] == total_assignments
                for scenario in scenarios
            ),
            "all_expert_loads_are_nonnegative": all(
                expert["assignments"] >= 0
                for scenario in scenarios
                for expert in scenario["expert_loads"]
            ),
            "all_ep_sizes_divide_num_experts": all(
                args.num_experts % ep_size == 0 for ep_size in args.ep_sizes
            ),
        },
        "metric_definitions": {
            "max_to_mean": "maximum assignments divided by mean assignments",
            "coefficient_of_variation": "population standard deviation divided by mean",
            "gini": "Gini coefficient over assignment counts; 0 is equal",
            "normalized_entropy": "Shannon entropy divided by log(entity count); 1 is equal",
            "top_10pct_share": "share held by ceil(10% of entities) with highest load",
        },
        "scenarios": scenarios,
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    write_csv(args.output_csv, scenarios)
    write_summary_csv(args.output_summary_csv, scenarios)
    print(f"Wrote {args.output_json}")
    print(f"Wrote {args.output_csv}")
    print(f"Wrote {args.output_summary_csv}")
    return 0 if all(result["quality_checks"].values()) else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, AssertionError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
