"""Strict, atomic JSON output and explicit representations of invalid numbers."""
import json
import math
import os
from pathlib import Path
import tempfile


def add_exception_note(error, message):
    """Retain secondary diagnostics on Python 3.10 as well as newer runtimes."""
    add_note = getattr(error, "add_note", None)
    if callable(add_note):
        add_note(message)
    else:
        error.__notes__ = [*getattr(error, "__notes__", []), message]


def diagnostic_value(value):
    """Keep invalid numeric evidence as text, never as a JSON NaN/Infinity token."""
    if isinstance(value, float) and not math.isfinite(value):
        return repr(value)
    if isinstance(value, dict):
        return {key: diagnostic_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [diagnostic_value(item) for item in value]
    return value


def write_json_atomic(path, data):
    """Serialize before touching the target; replace it only after a full write."""
    path = Path(path)
    payload = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=path.name + ".", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
