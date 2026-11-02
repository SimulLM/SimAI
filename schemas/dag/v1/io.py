"""Strict numeric and JSON reading used by the v1 graph boundary."""
import json
import math
from pathlib import Path


def finite_nonnegative(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"expected numeric finite nonnegative value: {value!r}")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError("value exceeds finite float range") from exc
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"expected finite nonnegative value: {value!r}")
    return number


def read_json(path):
    def reject(value):
        raise ValueError(f"non-finite JSON constant: {value}")

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    return json.loads(Path(path).read_text(encoding="utf-8"),
                      parse_constant=reject, object_pairs_hook=unique_object)
