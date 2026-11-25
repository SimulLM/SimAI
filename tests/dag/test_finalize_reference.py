"""Independent hand checks before the frozen controlled workload suite."""
import ast
import inspect
from copy import deepcopy
import pytest
from scripts.dag_finalize.common import ROOT,read
from scripts.dag_finalize.cpu_reference import predict
from scripts.dag_finalize.controlled import execute

DATA=read(ROOT/'configs/dag/finalize/controlled-cases.json')


def test_reference_has_no_application_or_dag_imports():
    from scripts.dag_finalize import cpu_reference
    tree=ast.parse(inspect.getsource(cpu_reference))
    modules=[n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
    modules += [a.name for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names]
    assert set(modules)<= {'decimal','heapq'}


def test_serial_reference_closed_form():
    case=DATA['cases'][0]
    result=predict(case,DATA['costs'])
    assert result['final_time_s']==DATA['costs']['compute_s']+DATA['costs']['residual_s']


@pytest.mark.parametrize('name',['requests','rounds','kv_slots'])
def test_invalid_counts_rejected(name):
    case=dict(DATA['cases'][0]);case[name]=0
    with pytest.raises(ValueError):predict(case,DATA['costs'])


def test_invalid_cost_rejected():
    costs=dict(DATA['costs'],compute_s=-1)
    with pytest.raises(ValueError):predict(DATA['cases'][0],costs)


@pytest.mark.parametrize('case',DATA['cases'],ids=lambda c:c['id'])
def test_controlled_executor_agrees_with_independent_model(case):
    reference=predict(case,DATA['costs']);runner,actual=execute(case,DATA['costs'])
    assert actual['completed']==reference['completed']
    assert actual['tasks']==reference['tasks']
    assert all(g.callback_count==1 for g in runner.executor.graphs.values())
    assert all(v['used']==0 for v in runner.executor._resources.usage_snapshot().values())


def test_capacity_really_delays_transfer_until_previous_decode_releases():
    case=next(c for c in DATA['cases'] if c['id']=='pd-backpressure')
    result=predict(case,DATA['costs'])
    tasks=result['tasks']
    assert any(v['start_s']>v['ready_s'] for k,v in tasks.items() if 'destination_reserve' in k)
    assert all(tasks[f'r{r:02d}/11.attention']['start_s']>=tasks[f'r{r:02d}/24.KVReady']['end_s'] for r in range(case['requests']))
