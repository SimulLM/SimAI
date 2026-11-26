import csv,json,pathlib
p=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/pre-response-recovery-20261126');assert pathlib.Path('/root/autodl-tmp/dag-handoff/pre-response-recovery.exit').read_text().strip()=='0';assert (p/'probe-exit').read_text().strip()=='2';assert json.loads((p/'fence-response.json').read_text())=={'error':'admission_fenced'}
warm=json.loads((p/'warmup.json').read_text());assert len(warm)==4 and all(x['status']==200 and x['done'] and x['usage']['completion_tokens']==8 for x in warm);last=max(x['complete_ns'] for x in warm)
syncs=[json.loads((p/f'sync-{x}.json').read_text()) for x in ('before','after')];assert all(x['status']=='completed' and len(x['workers'])==2 for x in syncs)
w=[{x['role']:x for x in s['workers']} for s in syncs];assert set(w[0])==set(w[1])=={'producer','consumer'} and all(w[0][r]['pid']==w[1][r]['pid'] for r in w[0]);assert all(last<=x['start_ns']<=x['end_ns'] for x in w[0].values())
obs=[json.loads(x) for x in (p/'probe/observations.jsonl').open()];assert len(obs)==4 and obs[-1]['monotonic_ns']-obs[0]['monotonic_ns']>=15e9
assert all(x['end_ns']<=obs[0]['monotonic_ns'] for x in w[0].values()) and all(x['start_ns']>=obs[-1]['monotonic_ns'] for x in w[1].values())
arrivals=[json.loads(x) for x in (p/'service/router-events.jsonl').open() if json.loads(x)['event']=='server_arrival'];assert len(arrivals)==4 and {x['request_id'] for x in arrivals}=={x['router_id'] for x in warm} and max(x['timestamp_ns'] for x in arrivals)<last
proc=[]
for name in ('before','after'):
 with (p/f'gpu-processes-{name}.csv').open() as f:proc.append({int(row[0].strip()):row[1].strip() for row in csv.reader(f) if len(row)>=2})
assert all(w[0][r]['pid'] in proc[0] and proc[0][w[0][r]['pid']]==proc[1].get(w[1][r]['pid']) for r in w[0]);assert proc[0][w[0]['producer']['pid']]!=proc[0][w[0]['consumer']['pid']]
rows=[]
for sample in obs:
 assert sample['router']['inflight']==sample['router']['unresolved_errors']==0
 for role in ('prefill','decode'):assert len(sample['servers'][role]['gauges'])==5 and all(v==0 for v in sample['servers'][role]['gauges'].values())
 for role in ('producer','consumer'):
  snap=[json.loads(x) for x in (p/'observer'/f"{role}-{w[0][role]['pid']}.jsonl").open()];prior=[x for x in snap if x['monotonic_ns']<=sample['monotonic_ns']];assert prior;x=prior[-1];assert (sample['monotonic_ns']-x['monotonic_ns'])/1e9<=1.5 and x['lock_acquired']
  assert x['queue_items']==x['buffer_bytes']==x['pipe_buffer_bytes']==x['signal_buffer_bytes']==0 and not any(x['active'].values()) and not any(x['pipe_active'].values())
  rows.append({'sample':sample['sample'],'role':role,'pid':x['pid'],'signal_active':x['signal_active'],'signal_counts':x['signal_counts'],'pipe_counts':x['pipe_counts']})
for role in ('producer','consumer'):
 v=[x for x in rows if x['role']==role];assert len({json.dumps(x['signal_counts'],sort_keys=True) for x in v})==1 and len({json.dumps(x['pipe_counts'],sort_keys=True) for x in v})==1
result={'status':'consistent_fenced_diagnostic_not_formal_readiness','warmups':4,'fenced_rejection_http':503,'window_seconds':(obs[-1]['monotonic_ns']-obs[0]['monotonic_ns'])/1e9,'worker_gpu_uuid':{r:proc[0][w[0][r]['pid']] for r in w[0]},'sync_before_and_after':True,'samples':rows,'limitations':['diagnostic router and observer modify running service','fence is process-local file check, not verified against requests already accepted before fence','host snapshots are non-atomic and signal listener may remain blocked','worker CUDA synchronization covers only prior submissions within each process','no crash or pre-response timeout cleanup test','formal service and preflight are not yet integrated']};pathlib.Path(__file__).with_name('recovery-audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
