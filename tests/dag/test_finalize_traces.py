"""Fractional Chrome time and independent device/stream interval semantics."""
from decimal import Decimal
import pytest
from scripts.dag_finalize.common import save
from scripts.dag_finalize.deepseek import analyze,length,overlap


def event(ts,dur,stream,name='flash_fwd',device=0):
    return dict(ph='X',cat='kernel',ts=ts,dur=dur,name=name,pid=100,tid=stream,args=dict(device=device,stream=stream))


def test_fractional_microseconds_are_not_truncated(tmp_path):
    path=tmp_path/'trace.json';save(path,dict(traceEvents=[event(.125,.375,1)]))
    result=analyze(path,unit='us',unit_evidence='unit-test')
    assert result['fractional_events_preserved']==1
    assert result['devices']['unknown:100:0']['kernel_union_s']==pytest.approx(.375e-6)
    assert not result['request_e2e_eligible']


def test_overlap_merges_streams_but_never_unsynchronized_devices(tmp_path):
    path=tmp_path/'trace.json';save(path,dict(traceEvents=[event(0,4,1),event(2,4,2,'internode::dispatch'),event(0,10,1,'internode::combine',device=1)]))
    result=analyze(path,unit='us',unit_evidence='unit-test')
    assert result['devices']['unknown:100:0']['kernel_union_s']==pytest.approx(6e-6)
    assert result['devices']['unknown:100:0']['compute_ep_kernel_overlap_s']==pytest.approx(2e-6)
    assert result['devices']['unknown:100:1']['compute_ep_kernel_overlap_s']==0


def test_same_device_number_in_different_processes_is_not_one_clock(tmp_path):
    a=event(0,4,1);b=event(1,3,2,'internode::dispatch');b['pid']=200
    path=tmp_path/'trace.json';save(path,dict(traceEvents=[a,b]))
    result=analyze(path,unit='us',unit_evidence='unit-test')
    assert len(result['devices'])==2
    assert all(d['compute_ep_kernel_overlap_s']==0 for d in result['devices'].values())


def test_duplicate_events_are_reported_and_invalid_timing_blocks_admission(tmp_path):
    path=tmp_path/'trace.json';a=event(0,1,1)
    save(path,dict(traceEvents=[a,a,event(0,-1,2)]))
    result=analyze(path,unit='us',unit_evidence='unit-test')
    assert result['duplicate_events_excluded']==1 and result['invalid_events']==1
    assert result['admission']=='blocked'


@pytest.mark.parametrize('unit,evidence',[(None,None),('ms','proof'),('us',None)])
def test_unit_must_be_explicit_and_proven(tmp_path,unit,evidence):
    with pytest.raises(ValueError,match='unit evidence'):analyze(tmp_path/'unused',unit=unit,unit_evidence=evidence)


def test_interval_union_closed_form():
    d=Decimal
    assert length([(d(0),d(3)),(d(2),d(5))])==5
    assert overlap([(d(0),d(3))],[(d(2),d(5))])==1
