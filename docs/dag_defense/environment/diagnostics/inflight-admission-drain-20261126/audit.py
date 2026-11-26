import csv,json,pathlib
p=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/inflight-admission-drain-20261126');assert pathlib.Path('/root/autodl-tmp/dag-handoff/inflight-admission-drain.exit').read_text().strip()=='0' and (p/'probe-exit').read_text().strip()=='2'
e=json.loads((p/'client-events.json').read_text());assert [x['event'] for x in e]==['fence','rejected','response','drained'];f,rejected,response,drained=e
assert f['state']['fenced'] and f['state']['active']==1 and f['state']['accepted']==5 and f['state']['finished']==4 and rejected['status']==503
assert response['status']==200 and response['done'] and response['usage']['prompt_tokens']==2048 and response['usage']['completion_tokens']==128 and f['time_ns']<response['end_ns']<=drained['time_ns']
assert drained['state']['fenced'] and drained['state']['active']==0 and drained['state']['accepted']==drained['state']['finished']==5
routes=list(map(json.loads,(p/'service/router-events.jsonl').open()));arrivals=[x for x in routes if x['event']=='server_arrival'];assert len(arrivals)==5 and sum(x.get('client_request_id')=='inflight-fence' for x in arrivals)==1
s=[json.loads((p/f'sync-{x}.json').read_text()) for x in ('before','after')];assert all(x['status']=='completed' for x in s);workers=[{x['role']:x for x in z['workers']} for z in s];assert set(workers[0])==set(workers[1])=={'producer','consumer'} and all(workers[0][r]['pid']==workers[1][r]['pid'] for r in workers[0])
obs=list(map(json.loads,(p/'probe/observations.jsonl').open()));assert len(obs)==4 and obs[-1]['monotonic_ns']-obs[0]['monotonic_ns']>=15e9 and all(x['end_ns']<=obs[0]['monotonic_ns'] for x in workers[0].values()) and all(x['start_ns']>=obs[-1]['monotonic_ns'] for x in workers[1].values())
proc=[]
for name in ('before','after'):
 with (p/f'gpu-{name}.csv').open() as f:proc.append({int(x[0].strip()):x[1].strip() for x in csv.reader(f) if len(x)>=2})
assert all(proc[0].get(workers[0][r]['pid']) and proc[0][workers[0][r]['pid']]==proc[1].get(workers[1][r]['pid']) for r in workers[0]) and proc[0][workers[0]['producer']['pid']]!=proc[0][workers[0]['consumer']['pid']]
counts={}
for o in obs:
 assert o['router']['inflight']==o['router']['unresolved_errors']==0 and all(all(v==0 for v in o['servers'][r]['gauges'].values()) for r in ('prefill','decode'))
 for role in workers[0]:
  rows=list(map(json.loads,(p/'observer'/f"{role}-{workers[0][role]['pid']}.jsonl").open()));x=next(x for x in reversed(rows) if x['monotonic_ns']<=o['monotonic_ns']);assert (o['monotonic_ns']-x['monotonic_ns'])/1e9<=1.5 and x['lock_acquired'] and x['queue_items']==x['buffer_bytes']==x['pipe_buffer_bytes']==x['signal_buffer_bytes']==0 and not any(x['active'].values()) and not any(x['pipe_active'].values())
  counts.setdefault(role,[]).append((json.dumps(x['pipe_counts'],sort_keys=True),json.dumps(x['signal_counts'],sort_keys=True)))
assert all(len(set(v))==1 for v in counts.values())
out={'status':'diagnostic_passed_not_formal_readiness','active_at_fence':1,'rejected_status':503,'drained_accepted':5,'drained_finished':5,'request_tokens':[2048,128],'window_s':(obs[-1]['monotonic_ns']-obs[0]['monotonic_ns'])/1e9,'limitations':['one successful in-flight request; not cancellation, crashes, or multiple routers','ASGI drain does not establish backend cleanup by itself','non-atomic snapshots and instrumentation perturbation','formal supervisor gate still not integrated']};pathlib.Path(__file__).with_name('audit.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
