"""The single shared fee mapping. No scheduling/readiness functions are patched."""
import bisect,collections,hashlib,json,math,pathlib,statistics

def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def require(v,s):
    if not v:raise ValueError(s)

class CompositeFees:
    def __init__(self,path):
        self.path=pathlib.Path(path);self.data=json.loads(self.path.read_text());self.points=collections.defaultdict(list)
        require(self.data['schema']=='composite-fees-v1','fee schema')
        for r in self.data['worker']:
            require(r['warmup_waves']>=10 and r['measured_waves']>=30,'unqualified fee '+str(r))
            require(math.isfinite(r['worker_ms']) and r['worker_ms']>0,'invalid worker fee')
            k=(r['phase'],r['input_tokens'],r['batch']);self.points[k].append(r)
        for k,rr in self.points.items():
            rr.sort(key=lambda r:r['context']);require(len({r['context'] for r in rr})==len(rr),'duplicate fee key '+str(k))
        require(self.data['ownership']=={'worker':['prepare','embedding','layers','rope','kv_cache_write','output_head','sampler','worker_host_wait'],
                                       'schedule':['engine_schedule'], 'output':['engine_output_processing'],
                                       'receiver':['kv_transport_receive','kv_install','consumer_bypass_head_sampler']},'physical component ownership differs')
        components=[x for rr in self.data['ownership'].values() for x in rr]
        require(len(components)==len(set(components)),'duplicate physical fee ownership')
    def get(self,phase,n,contexts,tokens):
        b=len(contexts);require(1<=b<=4 and len(tokens)==b,'unsupported batch')
        require(all(t==(n if phase=='prefill' else 1) for t in tokens),'chunked/mixed phase unsupported')
        require(phase in ('prefill','decode'),'unknown phase')
        context=0 if phase=='prefill' else sum(contexts)/b
        rr=self.points.get((phase,n,b),[]);require(rr,'MISSING_FEE '+str((phase,n,b,context)))
        xx=[r['context'] for r in rr];require(xx[0]<=context<=xx[-1],'OUTSIDE_MEASURED_DOMAIN '+str((phase,n,b,context,xx[0],xx[-1])))
        i=bisect.bisect_left(xx,context)
        if xx[i]==context:r=rr[i];return dict(r,queried_context=context,bracket=[context,context])
        lo,hi=rr[i-1],rr[i];alpha=(context-lo['context'])/(hi['context']-lo['context'])
        return {'phase':phase,'input_tokens':n,'batch':b,'context':context,'queried_context':context,'bracket':[lo['context'],hi['context']],
                **{k:lo[k]+alpha*(hi[k]-lo[k]) for k in ('worker_ms','schedule_ms','output_ms')}}
    def receiver(self,n):
        r=self.data['receiver'][str(n)];require(r['warmup_waves']>=10 and r['measured_waves']>=30,'unqualified receiver '+str(n))
        require(r['duration_s']>0 and math.isfinite(r['duration_s']),'bad receiver fee');return r['duration_s']

def build(samples,receiver_csv,out):
    import csv
    samples=pathlib.Path(samples);receiver_csv=pathlib.Path(receiver_csv);out=pathlib.Path(out)
    bystep=collections.defaultdict(dict)
    for line in samples.read_text().splitlines():
        r=json.loads(line);key=(r['input_tokens'],r['offered_batch'],r['wave'],r['step'])
        require(r['kind'] not in bystep[key],'duplicate measured interval '+str(key));bystep[key][r['kind']]=r
    grouped=collections.defaultdict(lambda:collections.defaultdict(list));interval_count=0
    for key,dd in bystep.items():
        require(set(dd)=={'schedule','worker','output'},'incomplete microbenchmark step '+str(key))
        s,w,o=(dd[k] for k in ('schedule','worker','output'))
        require(s['end_ns']<=w['start_ns']<w['end_ns']<=o['start_ns']<o['end_ns'],'overlapping composite source scopes '+str(key))
        require(w['batch']==w['offered_batch'],'unexpected microbenchmark batch')
        require(len(w['seq_lens'])==w['batch'] and len(set(w['seq_lens']))==1,'microbenchmark must have uniform contexts')
        c=0 if w['phase']=='prefill' else w['seq_lens'][0]
        k=(w['phase'],w['input_tokens'],w['batch'],c);grouped[k][w['wave']].append((w['duration_ms'],s['duration_ms'],o['duration_ms']));interval_count+=3
    worker=[]
    for k,waves in sorted(grouped.items()):
        warm=[v for w,v in waves.items() if w<10];measured=[v for w,v in waves.items() if w>=10]
        require(len(warm)==10 and len(measured)==30,'insufficient independent waves '+str(k))
        values=[[statistics.median(r[i] for r in wave) for wave in measured] for i in range(3)]
        worker.append(dict(zip(('phase','input_tokens','batch','context'),k),worker_ms=statistics.median(values[0]),schedule_ms=statistics.median(values[1]),output_ms=statistics.median(values[2]),warmup_waves=10,measured_waves=30,
                           worker_min_ms=min(values[0]),worker_max_ms=max(values[0])))
    with receiver_csv.open(newline='') as f:rx=list(csv.DictReader(f))
    receiver={}
    for n in (1024,2048):
        rr=[r for r in rx if int(r['length'])==n];warm=[r for r in rr if r['warmup']=='True'];measured=[r for r in rr if r['warmup']=='False']
        require(len(warm)==10 and len(measured)==30,'receiver coverage '+str(n))
        values=[]
        for r in rr:
            ts=[int(r[k]) for k in ('receive_start_ns','receive_return_ns','install_sync_ns','step_return_ns')]
            require(ts==sorted(ts),'receiver intervals reversed')
            if r['warmup']=='False':values.append((ts[-1]-ts[0])/1e9)
        receiver[str(n)]={'duration_s':statistics.median(values),'warmup_waves':10,'measured_waves':30,'min_s':min(values),'max_s':max(values),
                          'unit_of_work':'one request, batch1 inclusive receive/install/bypass first token','concurrency_assumption':'per-request serial envelope; no shared consumer-first-token batch saving modelled'}
    data={'schema':'composite-fees-v1','worker':worker,'receiver':receiver,
          'ownership':{'worker':['prepare','embedding','layers','rope','kv_cache_write','output_head','sampler','worker_host_wait'],'schedule':['engine_schedule'],'output':['engine_output_processing'],'receiver':['kv_transport_receive','kv_install','consumer_bypass_head_sampler']},
          'sources':[{'path':str(p),'sha256':sha(p)} for p in (samples,receiver_csv)],'disjoint_microbenchmark_intervals_checked':interval_count,
          'replacement':'Worker replaces layer, norm, RoPE, embedding/head, sampler and prepare fees; receiver replaces legacy bandwidth, install and first-token subfees. No enclosing interval plus subinterval addition.',
          'stages':{'1_producer_prefill':'One worker envelope per actual Prefill batch, with producer head and sampler; schedule/output CPU scopes once. Producer token is discarded by the router.',
                    '2_kv_and_consumer_token1':'One receiver envelope per request. Includes KV receive/install and consumer bypass head/sampler. No extra consumer first-token, head or sampler fee is charged.',
                    '3_consumer_tokens2_to128':'Exactly 127 normal Decode rounds per request; worker envelope for the actual formed batch, plus its schedule/output CPU scopes. Does not charge token1 again.'},
          'resource_assumptions':{'validation_status':'待验证近似 / unvalidated approximation', 'worker':'one opaque GPU permit for the entire synchronized host/device envelope; GPU can be idle inside this envelope','engine_cpu':'existing per-replica CPU prepare/finish resources; schedule/output disjoint in profiling','receiver':'existing transfer task holds source GPU, destination GPU and endpoints; serial per-request envelope; occupancy is an unvalidated approximation','internal_overlap':'none inside a composite; host/device overlap within the measurement counted once','between_batches':'existing scheduler and DAG resources unchanged'},
          'context_rule':'Linear interpolation of uniform measured worker envelopes by actual mean context, separately by phase, input length and actual batch. No extrapolation. Mixed-context vector reduced to mean is a modelling approximation.',
          'limitations':['Synchronous offline profiling perturbs overlap; fee is an inclusive service envelope, not isolated kernel time.','Receiver measured serial with eight-output requests; used only through first token, independent of later output length.','Per-request receiver assumption omits shared first-token batch savings and may overestimate concurrent cost.','Consumer prepare before receive, router/routing/IPC/stream tail outside measured envelopes remain unmodelled residuals; no E2E-derived correction.']}
    out.write_text(json.dumps(data,indent=2)+'\n');CompositeFees(out);return data

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--samples',required=True);p.add_argument('--receiver-csv',required=True);p.add_argument('--output',required=True);a=p.parse_args();d=build(a.samples,a.receiver_csv,a.output);print(json.dumps({'worker_points':len(d['worker']),'disjoint_intervals':d['disjoint_microbenchmark_intervals_checked'],'receiver':d['receiver']},indent=2))
