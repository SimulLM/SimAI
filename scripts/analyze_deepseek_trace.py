#!/usr/bin/env python3
"""Validate and summarize DeepSeek Prefill/Decode PyTorch profiler traces."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


EP_CATEGORIES = {"ep_notify_dispatch", "ep_dispatch", "ep_combine"}
COMPUTE_CATEGORIES = {
    "attention_compute",
    "expert_compute",
    "dense_gemm",
    "routing_and_elementwise",
}


def percentile(values: list[int], probability: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = round((len(ordered) - 1) * probability)
    return ordered[index]


def merge_intervals(intervals: Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[list[int]] = []
    for start, end in sorted(intervals):
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return [(start, end) for start, end in merged]


def interval_length(intervals: Iterable[tuple[int, int]]) -> int:
    return sum(end - start for start, end in merge_intervals(intervals))


def interval_overlap(
    left: Iterable[tuple[int, int]], right: Iterable[tuple[int, int]]
) -> int:
    left_merged = merge_intervals(left)
    right_merged = merge_intervals(right)
    left_index = right_index = overlap = 0
    while left_index < len(left_merged) and right_index < len(right_merged):
        left_start, left_end = left_merged[left_index]
        right_start, right_end = right_merged[right_index]
        overlap += max(0, min(left_end, right_end) - max(left_start, right_start))
        if left_end < right_end:
            left_index += 1
        else:
            right_index += 1
    return overlap


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def source_commit(path: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(path.parent), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def categorize_kernel(name: str) -> str:
    lowered = name.lower()
    if "get_dispatch_layout" in lowered:
        return "ep_dispatch_layout"
    if "internode::notify_dispatch" in lowered:
        return "ep_notify_dispatch"
    if "internode::dispatch" in lowered:
        return "ep_dispatch"
    if "internode::combine" in lowered:
        return "ep_combine"
    if any(token in lowered for token in ("flash::", "flash_fwd", "rotary_embedding", "mla_metadata")):
        return "attention_compute"
    if "grouped_gemm" in lowered or "(dpsk::gemm::gemmtype)1" in lowered or "(dpsk::gemm::gemmtype)2" in lowered:
        return "expert_compute"
    if any(token in lowered for token in ("dpsk::gemm", "cublas", "cutlass::kernel", "xmma_gemm")):
        return "dense_gemm"
    if any(
        token in lowered
        for token in (
            "layer_norm",
            "top2_sum_gate",
            "clean_and_count_expert",
            "get_fused_mapping",
            "expand_to_fused",
            "swiglu",
        )
    ):
        return "routing_and_elementwise"
    return "other_gpu_kernel"


def event_interval(event: dict[str, Any]) -> tuple[int, int]:
    start = int(event["ts"])
    return start, start + int(event["dur"])


def analyze_pairs(events: list[dict[str, Any]], name_token: str) -> dict[str, Any]:
    selected = [event for event in events if name_token in event["name"].lower()]
    pairs = list(zip(selected[0::2], selected[1::2]))
    issue_duration = [int(first["dur"]) for first, _ in pairs]
    between_calls = [
        int(second["ts"]) - (int(first["ts"]) + int(first["dur"]))
        for first, second in pairs
    ]
    followup_duration = [int(second["dur"]) for _, second in pairs]
    return {
        "event_count": len(selected),
        "pair_count": len(pairs),
        "unpaired_event_count": len(selected) % 2,
        "pairing_rule": "chronological adjacent pairs; descriptive only",
        "first_call_duration_us_median": statistics.median(issue_duration) if pairs else None,
        "between_calls_us_median": statistics.median(between_calls) if pairs else None,
        "between_calls_us_p95": percentile(between_calls, 0.95),
        "second_call_duration_us_median": statistics.median(followup_duration) if pairs else None,
        "second_call_duration_us_p95": percentile(followup_duration, 0.95),
        "second_call_duration_us_max": max(followup_duration) if pairs else None,
    }


def analyze_trace(label: str, path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)

    trace_events = data.get("traceEvents")
    if not isinstance(trace_events, list):
        raise ValueError(f"{path}: traceEvents is missing or is not a list")

    complete_events = [event for event in trace_events if event.get("ph") == "X"]
    missing_timing = [
        index
        for index, event in enumerate(complete_events)
        if not isinstance(event.get("ts"), (int, float))
        or not isinstance(event.get("dur"), (int, float))
    ]
    negative_duration = [
        index
        for index, event in enumerate(complete_events)
        if isinstance(event.get("dur"), (int, float)) and event["dur"] < 0
    ]
    kernels = sorted(
        [
            event
            for event in complete_events
            if event.get("cat") == "kernel" and event.get("name") and "ts" in event and "dur" in event
        ],
        key=lambda event: (event["ts"], event["tid"]),
    )
    if not kernels:
        raise ValueError(f"{path}: no complete GPU kernel events found")

    trace_start = int(kernels[0]["ts"])
    trace_end = max(int(event["ts"] + event["dur"]) for event in kernels)
    by_category: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in kernels:
        by_category[categorize_kernel(event["name"])].append(event)

    ep_intervals = [
        event_interval(event)
        for category in EP_CATEGORIES
        for event in by_category.get(category, [])
    ]
    compute_intervals = [
        event_interval(event)
        for category, events in by_category.items()
        if category in COMPUTE_CATEGORIES
        for event in events
    ]
    ep_union = interval_length(ep_intervals)
    compute_union = interval_length(compute_intervals)
    direct_overlap = interval_overlap(ep_intervals, compute_intervals)

    category_rows = []
    for category, events in sorted(by_category.items()):
        durations = [int(event["dur"]) for event in events]
        intervals = [event_interval(event) for event in events]
        category_union = interval_length(intervals)
        if category in EP_CATEGORIES:
            counterpart = compute_intervals
            relationship = "directly overlaps GPU compute" if interval_overlap(intervals, counterpart) else "no direct GPU-kernel overlap"
        elif category == "ep_dispatch_layout":
            counterpart = ep_intervals
            relationship = "prepares EP dispatch"
        else:
            counterpart = ep_intervals
            relationship = "overlaps EP kernels" if interval_overlap(intervals, counterpart) else "no direct EP-kernel overlap"
        overlap = interval_overlap(intervals, counterpart)
        category_rows.append(
            {
                "trace": label,
                "category": category,
                "first_start_us": int(events[0]["ts"]) - trace_start,
                "event_count": len(events),
                "median_duration_us": statistics.median(durations),
                "p95_duration_us": percentile(durations, 0.95),
                "summed_duration_us": sum(durations),
                "union_duration_us": category_union,
                "direct_overlap_us": overlap,
                "overlap_pct_of_category_union": round(100 * overlap / category_union, 3)
                if category_union
                else 0.0,
                "streams": sorted({int(event["tid"]) for event in events}),
                "relationship": relationship,
            }
        )

    distributed = data.get("distributedInfo", {})
    devices = data.get("deviceProperties", [])
    thread_names = {
        str(event.get("tid")): event.get("args", {}).get("name")
        for event in trace_events
        if event.get("ph") == "M" and event.get("name") == "thread_name"
    }
    quality_checks = {
        "trace_events_is_nonempty": bool(trace_events),
        "complete_events_have_numeric_timing": not missing_timing,
        "complete_events_have_nonnegative_duration": not negative_duration,
        "gpu_kernel_events_are_present": bool(kernels),
        "distributed_world_size_is_positive": isinstance(distributed.get("world_size"), int)
        and distributed["world_size"] > 0,
        "rank_is_zero": distributed.get("rank") == 0,
        "device_metadata_is_present": bool(devices),
    }

    result = {
        "trace": label,
        "source": {
            "path": path.as_posix(),
            "sha256": sha256(path),
            "size_bytes": path.stat().st_size,
            "repository_commit": source_commit(path),
        },
        "metadata": {
            "schema_version": data.get("schemaVersion"),
            "trace_name": data.get("traceName"),
            "backend": distributed.get("backend"),
            "rank": distributed.get("rank"),
            "world_size": distributed.get("world_size"),
            "device": devices[0].get("name") if devices else None,
            "gpu_streams": thread_names,
        },
        "data_quality": {
            "status": "pass" if all(quality_checks.values()) else "fail",
            "checks": quality_checks,
            "missing_timing_event_count": len(missing_timing),
            "negative_duration_event_count": len(negative_duration),
            "invalid_named_event_count": sum(event.get("name") == "INVALID" for event in complete_events),
        },
        "event_counts": {
            "all_trace_events": len(trace_events),
            "complete_events": len(complete_events),
            "gpu_kernel_events": len(kernels),
            "by_trace_category": dict(sorted(Counter(event.get("cat", "<none>") for event in trace_events).items())),
        },
        "gpu_timeline": {
            "origin_timestamp_us": trace_start,
            "span_us": trace_end - trace_start,
            "ep_kernel_union_us": ep_union,
            "compute_kernel_union_us": compute_union,
            "direct_overlap_us": direct_overlap,
            "ep_kernel_direct_overlap_pct": round(100 * direct_overlap / ep_union, 3) if ep_union else 0.0,
            "measurement_note": (
                "Union-based overlap between visible EP kernels and explicitly classified attention, "
                "expert, dense-GEMM, routing, and elementwise GPU kernels. It excludes unclassified "
                "kernels and does not measure RDMA activity after a launch kernel frees the GPU SMs."
            ),
        },
        "key_event_categories": category_rows,
    }
    if label == "decode":
        result["decode_adjacent_pair_observations"] = {
            "dispatch_ll": analyze_pairs(kernels, "dispatch_ll"),
            "combine_ll": analyze_pairs(kernels, "combine_ll"),
            "interpretation_limit": (
                "Adjacent-call pairing exposes the repeated two-call shape but does not prove network "
                "completion or isolate pure wait time without DeepEP correlation markers."
            ),
        }
    return result


def write_csv(path: Path, traces: list[dict[str, Any]]) -> None:
    fields = [
        "trace",
        "ep_world_size",
        "category",
        "first_start_us",
        "event_count",
        "median_duration_us",
        "p95_duration_us",
        "summed_duration_us",
        "union_duration_us",
        "direct_overlap_us",
        "overlap_pct_of_category_union",
        "streams",
        "relationship",
        "source_sha256",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for trace in traces:
            for row in trace["key_event_categories"]:
                writer.writerow(
                    {
                        **row,
                        "ep_world_size": trace["metadata"]["world_size"],
                        "streams": ",".join(str(stream) for stream in row["streams"]),
                        "source_sha256": trace["source"]["sha256"],
                    }
                )


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prefill",
        type=Path,
        default=repo_root / "tmp" / "deepseek-profile-data" / "prefill.json",
    )
    parser.add_argument(
        "--decode",
        type=Path,
        default=repo_root / "tmp" / "deepseek-profile-data" / "decode.json",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=repo_root / "docs" / "data" / "deepseek_trace_analysis.json",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=repo_root / "docs" / "data" / "deepseek_key_events.csv",
    )
    args = parser.parse_args()

    traces = [
        analyze_trace("prefill", args.prefill.resolve()),
        analyze_trace("decode", args.decode.resolve()),
    ]
    for trace in traces:
        try:
            trace["source"]["path"] = str(
                Path(trace["source"]["path"]).relative_to(repo_root)
            ).replace("\\", "/")
        except ValueError:
            pass

    result = {
        "schema_version": 1,
        "metric_definitions": {
            "duration_unit": "microseconds",
            "first_start_us": "start relative to the first GPU kernel in the same trace",
            "summed_duration_us": "sum of event durations; may double-count concurrency",
            "union_duration_us": "length of merged event intervals; does not double-count concurrency",
            "direct_overlap_us": "intersection of visible EP and non-EP GPU kernel interval unions",
        },
        "traces": traces,
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    write_csv(args.output_csv, traces)
    print(f"Wrote {args.output_json}")
    print(f"Wrote {args.output_csv}")
    return 0 if all(trace["data_quality"]["status"] == "pass" for trace in traces) else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
