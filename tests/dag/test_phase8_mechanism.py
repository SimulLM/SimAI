"""Independent queue arithmetic, zero-fit cost identity and frozen evidence."""
import ast
from copy import deepcopy
import inspect
import json

import pytest

from scripts.dag_phase8 import queue_reference
from scripts.dag_phase8.mechanism_experiment import check_frozen, digest, save, summarize


def contract():
    return dict(tokens={"8": {"0": dict(total_s=.005, components_ms=dict(
        pipeline_parallel_communication_time=2, sampler_e2e_time=0, process_model_outputs_time=0, ray_comm_time=0)),
        "1": dict(total_s=.004, components_ms=dict(pipeline_parallel_communication_time=0))}})


def test_shared_server_wait_and_private_control_have_same_service():
    case = dict(tokens=[8, 8], endpoint="shared", arrival_gap_s=.001)
    shared = queue_reference.predict(case, contract())
    assert [r["request_e2e_s"] for r in shared] == pytest.approx([.009, .010])
    assert [r["resource_wait_s"] for r in shared] == pytest.approx([0, .001])
    private = queue_reference.predict(dict(case, endpoint="private"), contract())
    assert [r["request_e2e_s"] for r in private] == pytest.approx([.009, .009])
    assert [r["communication_service_s"] for r in private] == [r["communication_service_s"] for r in shared]


def test_reference_orders_by_network_ready_time_and_keeps_post_cpu():
    costs = contract()
    costs["tokens"]["16"] = deepcopy(costs["tokens"]["8"])
    costs["tokens"]["16"]["0"]["total_s"] = .010
    rows = queue_reference.predict(dict(tokens=[16, 8], endpoint="shared", arrival_gap_s=.001), costs)
    assert rows[1]["communication_start_s"] < rows[0]["communication_start_s"]
    costs["tokens"]["8"]["0"]["total_s"] = .006
    costs["tokens"]["8"]["0"]["components_ms"]["sampler_e2e_time"] = 1
    [row] = queue_reference.predict(dict(tokens=[8], endpoint="shared", arrival_gap_s=0), costs)
    assert row["communication_ready_s"] == pytest.approx(.003)
    assert row["request_e2e_s"] == pytest.approx(.010)


def test_reference_is_standalone_and_has_no_dag_or_simulator_import():
    tree = ast.parse(inspect.getsource(queue_reference))
    modules = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    modules += [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]
    assert set(modules) <= {"argparse", "decimal", "json", "pathlib"}


def test_frozen_reference_cannot_be_overwritten_silently(tmp_path):
    path = tmp_path / "reference.json"
    save(path, dict(value=1))
    save(tmp_path / "experiment-freeze.json", dict(input_sha256={"reference.json": digest(path)}))
    check_frozen(tmp_path)
    save(path, dict(value=2))
    with pytest.raises(ValueError, match="frozen input"):
        check_frozen(tmp_path)


def test_summary_keeps_controls_and_all_validation_requests():
    rows = [dict(case=name, role=role, legacy_relative_error=old, dag_expanded_relative_error=new,
                 reference_wait_s=wait, outcome=outcome) for name, role, old, new, wait, outcome in
            [("control", "control", 0, 0, 0, "tied"), ("shared", "validation", 0, 0, 0, "tied"),
             ("shared", "validation", .1, 0, .001, "improved")]]
    results = summarize(rows)
    assert len(results) == 2
    assert results[1]["requests"] == 2 and results[1]["legacy_mean_relative_error"] == .05
    assert results[1]["improved"] == 1 and results[1]["tied"] == 1
