"""Negative acceptance checks for domain, physical ownership and interval overlap."""
import copy,json,pathlib,tempfile
from composite_fee import CompositeFees,build

OWN={'worker':['prepare','embedding','layers','rope','kv_cache_write','output_head','sampler','worker_host_wait'],'schedule':['engine_schedule'],'output':['engine_output_processing'],'receiver':['consumer_bypass_prepare','kv_transport_receive','kv_install','consumer_bypass_head_sampler']}
def fixture():
    return {'schema':'composite-fees-v1','ownership':copy.deepcopy(OWN),'worker':[{'phase':'decode','input_tokens':2048,'batch':3,'context':c,'worker_ms':float(c-2040),'schedule_ms':.1,'output_ms':.2,'warmup_waves':10,'measured_waves':30} for c in (2049,2175)],'receiver':{'2048':{'duration_s':.04,'warmup_waves':10,'measured_waves':30}}}
def rejected(fn,expected):
    try:fn()
    except ValueError as e:assert expected in str(e),str(e)
    else:raise AssertionError('invalid evidence was accepted')
def test_actual_batch_domain_and_no_duplicate_first_token_scope():
    with tempfile.TemporaryDirectory() as d:
        p=pathlib.Path(d)/'fees.json';p.write_text(json.dumps(fixture()));f=CompositeFees(p)
        assert f.get('decode',2048,[2050,2051,2052],[1,1,1])['queried_context']==2051
        assert f.receiver(2048)==.04
        rejected(lambda:f.get('decode',2048,[2176]*3,[1]*3),'OUTSIDE_MEASURED_DOMAIN')
        rejected(lambda:f.get('decode',2048,[2050]*2,[1]*2),'MISSING_FEE')
        rejected(lambda:f.get('prefill',2048,[0]*3,[2896]*3),'chunked/mixed')
        x=fixture();x['ownership']['receiver'].append('sampler');p.write_text(json.dumps(x))
        rejected(lambda:CompositeFees(p),'physical component ownership differs')
        x=fixture();x['worker'][0]['measured_waves']=29;p.write_text(json.dumps(x))
        rejected(lambda:CompositeFees(p),'unqualified fee')
def test_enclosing_source_intervals_cannot_be_summed():
    with tempfile.TemporaryDirectory() as d:
        p=pathlib.Path(d);rows=[]
        for kind,start,end in [('schedule',0,10),('worker',9,20),('output',20,30)]:
            rows.append(dict(kind=kind,input_tokens=2048,offered_batch=3,wave=0,step=1,start_ns=start,end_ns=end,batch=3,phase='decode',seq_lens=[2049]*3,duration_ms=1))
        (p/'samples').write_text(''.join(json.dumps(r)+'\n' for r in rows))
        rejected(lambda:build(p/'samples',p/'unused.csv',p/'out'),'overlapping composite source scopes')
if __name__=='__main__':
    test_actual_batch_domain_and_no_duplicate_first_token_scope();test_enclosing_source_intervals_cannot_be_summed();print('composite fee acceptance negative tests passed')
