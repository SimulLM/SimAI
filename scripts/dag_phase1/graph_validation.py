"""Backward-compatible phase-1 entry point for shared DAG v1 validation."""
import sys
from common import ROOT

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from schemas.dag.v1.validation import (  # noqa: E402,F401
    SCHEMA, SCHEMA_PATH, SCALES, VALIDATOR, validate_graph, validate_expectation,
)
