"""Independent queue arithmetic, zero-fit cost identity and frozen evidence."""
import ast
from copy import deepcopy
import inspect
import json

import pytest

from scripts.dag_phase8 import queue_reference
from scripts.dag_phase8.mechanism_experiment import (check_frozen, digest, save, summarize, arrivals,
                                                     validate_spec, error_statistics, group_summary, ROOT)


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


def test_predeclared_queue_policies_can_disagree_without_changing_service_costs():
    costs=contract()
    for token,total,transfer in ((8,.005,5),(16,.004,1),(24,.003,1)):
        costs['tokens'][str(token)]=deepcopy(costs['tokens']['8'])
        costs['tokens'][str(token)]['0']['total_s']=total
        costs['tokens'][str(token)]['0']['components_ms']['pipeline_parallel_communication_time']=transfer
    case=dict(tokens=[8,16,24],endpoint='shared',arrival_gap_s=0)
    fcfs=queue_reference.predict(case,costs)
    priority=queue_reference.predict(case,costs,'submission_priority')
    assert fcfs[2]['communication_start_s'] < fcfs[1]['communication_start_s']
    assert priority[1]['communication_start_s'] < priority[2]['communication_start_s']
    assert [row['communication_service_s'] for row in fcfs]==[row['communication_service_s'] for row in priority]


def test_expanded_suite_counts_diversity_and_frozen_random_seeds():
    spec=json.loads((ROOT/'configs/dag/phase8/mechanism-expanded.json').read_text())
    validate_spec(spec)
    assert len(spec['cases'])==23
    assert sum(len(case['tokens']) for case in spec['cases'])==311
    assert sum(len(case['tokens']) for case in spec['cases'] if case['role']=='validation')==262
    assert max(len(case['tokens']) for case in spec['cases'])==32
    assert set(spec['reference_policies'])=={'fcfs','submission_priority'}
    assert len({case['seed'] for case in spec['cases'] if 'seed' in case})==3
    assert {case['family'] for case in spec['cases']}=={'control','scale','arrival','payload','ordering'}


def test_explicit_arrivals_are_used_and_unsorted_arrivals_rejected():
    spec=json.loads((ROOT/'configs/dag/phase8/mechanism-expanded.json').read_text())
    case=deepcopy(spec['cases'][0]);case.update(tokens=[8,16],arrivals_s=[.001,.002])
    assert arrivals(case)==[.001,.002]
    spec['cases']=[case];validate_spec(spec)
    case['arrivals_s']=[.002,.001]
    with pytest.raises(ValueError,match='arrivals'):validate_spec(spec)


def test_error_statistics_preserve_worst_case_and_regressions():
    rows=[dict(case='x',family='ordering',role='validation',legacy_relative_error=.1,
               dag_expanded_relative_error=value,legacy_absolute_error_s=.001,dag_expanded_absolute_error_s=value*.01,
               dag_priority_relative_error=0,reference_wait_s=.01,outcome=outcome)
          for value,outcome in ((.05,'improved'),(.5,'regressed'))]
    stats=error_statistics(rows,'dag_expanded')
    assert stats['mean_relative_error']==pytest.approx(.275)
    assert stats['p95_relative_error']==pytest.approx(.4775)
    assert stats['max_relative_error']==.5
    [summary]=group_summary(rows)
    assert summary['improved']==summary['regressed']==1 and summary['requests']==2


def test_fcfs_extension_preserves_original_committed_reference_values():
    from scripts.dag_phase8.compare_versions import Evidence
    evidence=Evidence(archive=ROOT/'docs/dag/phase8/artifacts/20261119-phase8-dag-mechanism.zip')
    try:
        costs=evidence.json('cost-contract.json')
        for case in evidence.json('experiment.json')['cases']:
            expected=evidence.json('cases/'+case['name']+'/reference.json')['requests']
            assert queue_reference.predict(case,costs)==expected
    finally:evidence.close()
