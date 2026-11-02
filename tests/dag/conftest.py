from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vidur-alibabacloud"))

import pytest


@pytest.fixture
def graph_factory():
    from schemas.dag.v1.contracts import CostEstimate, GraphContext, GraphFragment, Placement, TaskSpec

    def make(durations, edges=(), graph_id="synthetic"):
        tasks = []
        for tid, duration in durations.items():
            tasks.append(TaskSpec(tid, "compute", Placement(), (),
                                  CostEstimate(duration, "synthetic_test", duration, "s", 1,
                                               "test-generated constant", ("compute",))))
        tasks.append(TaskSpec("terminal", "sync", Placement(), (),
                              CostEstimate(0, "synthetic_test", 0, "s", 1,
                                           "test terminal", ("sync",))))
        sources = {a for a, _ in edges}
        merged = tuple(edges) + tuple((tid, "terminal") for tid in durations if tid not in sources)
        return GraphFragment("1.0", graph_id, GraphContext("b", 0, "r", 0, ("q",)),
                             tuple(tasks), merged, "terminal")
    return make
