#!/usr/bin/env python3
"""Validate a SimAI workload file and summarize its communication operations."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


COLUMNS = (
    "name",
    "dependency",
    "forward_compute_time",
    "forward_comm_type",
    "forward_comm_size",
    "input_gradient_compute_time",
    "input_gradient_comm_type",
    "input_gradient_comm_size",
    "weight_gradient_compute_time",
    "weight_gradient_comm_type",
    "weight_gradient_comm_size",
    "weight_update_time",
)

COMM_PHASES = (
    ("forward", 3, 4),
    ("input_gradient", 6, 7),
    ("weight_gradient", 9, 10),
)

KNOWN_COMM_PATTERN = re.compile(
    r"^(?:NONE|(?:ALLREDUCE|ALLTOALL|ALLREDUCEALLTOALL|ALLGATHER|REDUCESCATTER)(?:_EP|_DP_EP)?)$"
)


def parse_header(header: str) -> tuple[str, dict[str, int]]:
    tokens = header.split()
    if not tokens:
        raise ValueError("workload header is empty")

    parameters: dict[str, int] = {}
    index = 1
    while index < len(tokens):
        key = tokens[index].removesuffix(":")
        if index + 1 >= len(tokens):
            raise ValueError(f"header parameter {key!r} has no value")
        try:
            parameters[key] = int(tokens[index + 1])
        except ValueError as exc:
            raise ValueError(
                f"header parameter {key!r} is not an integer: {tokens[index + 1]!r}"
            ) from exc
        index += 2
    return tokens[0], parameters


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def gib(byte_count: int) -> float:
    return round(byte_count / (1024**3), 6)


def analyze(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    normalized = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    lines = normalized.decode("utf-8-sig").splitlines()
    if len(lines) < 2:
        raise ValueError("workload must contain a header and a declared record count")

    run_type, parameters = parse_header(lines[0])
    try:
        declared_count = int(lines[1].strip())
    except ValueError as exc:
        raise ValueError(f"invalid declared record count: {lines[1]!r}") from exc

    rows = lines[2:]
    field_count_errors: list[dict[str, int]] = []
    numeric_parse_errors: list[dict[str, Any]] = []
    negative_value_errors: list[dict[str, Any]] = []
    none_with_nonzero_size: list[dict[str, Any]] = []
    unknown_comm_types: list[dict[str, Any]] = []
    zero_size_communication: Counter[tuple[str, str]] = Counter()
    parsed_rows: list[list[Any]] = []

    numeric_indexes = (1, 2, 4, 5, 7, 8, 10, 11)
    for record_index, line in enumerate(rows, start=1):
        fields = line.split("\t")
        if len(fields) != len(COLUMNS):
            field_count_errors.append(
                {"record_index": record_index, "actual_field_count": len(fields)}
            )
            continue

        parsed: list[Any] = fields.copy()
        row_has_parse_error = False
        for column_index in numeric_indexes:
            try:
                parsed[column_index] = int(fields[column_index])
            except ValueError:
                numeric_parse_errors.append(
                    {
                        "record_index": record_index,
                        "column": COLUMNS[column_index],
                        "value": fields[column_index],
                    }
                )
                row_has_parse_error = True
        if row_has_parse_error:
            continue

        for column_index in numeric_indexes[1:]:
            if parsed[column_index] < 0:
                negative_value_errors.append(
                    {
                        "record_index": record_index,
                        "column": COLUMNS[column_index],
                        "value": parsed[column_index],
                    }
                )

        for phase, comm_index, size_index in COMM_PHASES:
            comm_type = parsed[comm_index]
            comm_size = parsed[size_index]
            if not KNOWN_COMM_PATTERN.fullmatch(comm_type):
                unknown_comm_types.append(
                    {
                        "record_index": record_index,
                        "phase": phase,
                        "comm_type": comm_type,
                    }
                )
            if comm_type == "NONE" and comm_size != 0:
                none_with_nonzero_size.append(
                    {
                        "record_index": record_index,
                        "phase": phase,
                        "comm_size": comm_size,
                    }
                )
            elif comm_type != "NONE" and comm_size == 0:
                zero_size_communication[(phase, comm_type)] += 1

        parsed_rows.append(parsed)

    critical_checks = {
        "declared_count_matches_actual": declared_count == len(rows),
        "all_records_have_12_fields": not field_count_errors,
        "all_numeric_fields_parse": not numeric_parse_errors,
        "numeric_values_are_nonnegative_except_dependency": not negative_value_errors,
        "all_communication_types_are_known": not unknown_comm_types,
        "none_communication_has_zero_size": not none_with_nonzero_size,
    }

    by_phase_type: defaultdict[tuple[str, str], dict[str, int]] = defaultdict(
        lambda: {"operation_count": 0, "declared_bytes": 0}
    )
    layer_names = Counter()
    compute_times = Counter()
    for row in parsed_rows:
        layer_names[row[0]] += 1
        for compute_index in (2, 5, 8, 11):
            compute_times[row[compute_index]] += 1
        for phase, comm_index, size_index in COMM_PHASES:
            key = (phase, row[comm_index])
            by_phase_type[key]["operation_count"] += 1
            by_phase_type[key]["declared_bytes"] += row[size_index]

    phase_rows = []
    for (phase, comm_type), values in sorted(by_phase_type.items()):
        phase_rows.append(
            {
                "phase": phase,
                "comm_type": comm_type,
                **values,
                "declared_gib": gib(values["declared_bytes"]),
            }
        )

    alltoall_totals: defaultdict[str, dict[str, int]] = defaultdict(
        lambda: {"operation_count": 0, "declared_bytes": 0}
    )
    alltoall_by_layer: defaultdict[tuple[str, str, str], dict[str, Any]] = defaultdict(
        lambda: {"operation_count": 0, "declared_bytes": 0, "message_sizes": set()}
    )
    for row in phase_rows:
        if row["comm_type"] in {"ALLTOALL", "ALLTOALL_EP"}:
            values = alltoall_totals[row["comm_type"]]
            values["operation_count"] += row["operation_count"]
            values["declared_bytes"] += row["declared_bytes"]

    for row in parsed_rows:
        for phase, comm_index, size_index in COMM_PHASES:
            comm_type = row[comm_index]
            if comm_type in {"ALLTOALL", "ALLTOALL_EP"}:
                values = alltoall_by_layer[(phase, comm_type, row[0])]
                values["operation_count"] += 1
                values["declared_bytes"] += row[size_index]
                values["message_sizes"].add(row[size_index])

    alltoall_rows = []
    for comm_type in ("ALLTOALL", "ALLTOALL_EP"):
        values = alltoall_totals[comm_type]
        alltoall_rows.append(
            {
                "comm_type": comm_type,
                **values,
                "declared_gib": gib(values["declared_bytes"]),
            }
        )

    ordinary_bytes = alltoall_totals["ALLTOALL"]["declared_bytes"]
    expert_bytes = alltoall_totals["ALLTOALL_EP"]["declared_bytes"]
    ratio = round(expert_bytes / ordinary_bytes, 6) if ordinary_bytes else None

    zero_size_rows = [
        {"phase": phase, "comm_type": comm_type, "operation_count": count}
        for (phase, comm_type), count in sorted(zero_size_communication.items())
    ]

    return {
        "schema_version": 1,
        "source": {
            "path": path.as_posix(),
            "raw_sha256": sha256(raw),
            "normalized_lf_sha256": sha256(normalized),
        },
        "format": {
            "run_type": run_type,
            "header_parameters": parameters,
            "columns": list(COLUMNS),
            "declared_record_count": declared_count,
            "actual_record_count": len(rows),
            "valid_record_count": len(parsed_rows),
        },
        "data_quality": {
            "status": "pass" if all(critical_checks.values()) else "fail",
            "checks": critical_checks,
            "field_count_errors": field_count_errors,
            "numeric_parse_errors": numeric_parse_errors,
            "negative_value_errors": negative_value_errors,
            "unknown_comm_types": unknown_comm_types,
            "none_with_nonzero_size": none_with_nonzero_size,
            "zero_size_non_none_communication": zero_size_rows,
        },
        "summary": {
            "by_phase_and_comm_type": phase_rows,
            "alltoall": {
                "by_type": alltoall_rows,
                "by_phase_type_and_layer": [
                    {
                        "phase": phase,
                        "comm_type": comm_type,
                        "layer_name": layer_name,
                        "operation_count": values["operation_count"],
                        "message_sizes_bytes": sorted(values["message_sizes"]),
                        "declared_bytes": values["declared_bytes"],
                        "declared_gib": gib(values["declared_bytes"]),
                    }
                    for (phase, comm_type, layer_name), values in sorted(
                        alltoall_by_layer.items()
                    )
                ],
                "combined_declared_bytes": ordinary_bytes + expert_bytes,
                "combined_declared_gib": gib(ordinary_bytes + expert_bytes),
                "alltoall_ep_to_alltoall_byte_ratio": ratio,
            },
            "distinct_layer_names": len(layer_names),
            "top_layer_names": [
                {"name": name, "record_count": count}
                for name, count in layer_names.most_common(15)
            ],
            "compute_time_value_counts": [
                {"value": value, "occurrence_count": count}
                for value, count in sorted(compute_times.items())
            ],
        },
        "metric_note": (
            "declared_bytes sums the comm_size operands stored in the workload records; "
            "it is not measured link traffic, per-rank traffic, or fabric-wide bytes."
        ),
    }


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input",
        nargs="?",
        type=Path,
        default=repo_root / "example" / "workload_analytical.txt",
        help="SimAI workload file to inspect",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=repo_root / "docs" / "data" / "week1_workload_analysis.json",
        help="JSON output path; pass '-' to print only to stdout",
    )
    args = parser.parse_args()

    input_path = args.input.resolve()
    result = analyze(input_path)
    result["source"]["path"] = str(
        input_path.relative_to(repo_root) if input_path.is_relative_to(repo_root) else input_path
    ).replace("\\", "/")
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"

    if str(args.output) == "-":
        sys.stdout.write(payload)
    else:
        output_path = args.output.resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload, encoding="utf-8", newline="\n")
        print(f"Wrote {output_path}")

    return 0 if result["data_quality"]["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
