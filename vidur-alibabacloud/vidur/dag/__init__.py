"""Dependency-driven DAG execution, independent of inference/model imports."""
from pathlib import Path
import sys

# In-place original CLI runs from vidur-alibabacloud; contracts live at repo root.
_repository_root = str(Path(__file__).resolve().parents[3])
if _repository_root not in sys.path:
    sys.path.insert(0, _repository_root)
