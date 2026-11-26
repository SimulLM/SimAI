import json,pathlib,glob
p=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/signal-observer-20261126');out=pathlib.Path(__file__).parent
assert (p/'exit').read_text().strip()=='0' and (p/'probe-exit').read_text().strip()=='2'
warm=json.loads((p/'warmup.json').read_text());assert len(warm)==4 and len({x['router_id'] for x in warm})==4
assert all(x['status']==200 and x['done'] and x['usage']['completion_tokens']==8 for x in warm)
sync=json.loads((p/'worker-sync.json').read_text());assert sync['status']=='completed' and len(sync['workers'])==2
workers={w['role']:w for w in sync['workers']};assert set(workers)=={'producer','consumer'} and len({x['pid'] for x in workers.values()})==2
obs=[json.loads(l) for l in (p/'probe/observations.jsonl').open()];assert len(obs)==4
routes=[json.loads(l) for l in (p/'service/router-events.jsonl').open()];arrivals=[x for x in routes if x['event']=='server_arrival'];assert len(arrivals)==4 and {x['request_id'] for x in arrivals}=={x['router_id'] for x in warm}
last=max(x['complete_ns'] for x in warm);first=obs[0]['monotonic_ns'];assert all(last<=w['start_ns']<=w['end_ns']<=first for w in workers.values())
rows=[]
for sample in obs:
 assert sample['router']['inflight']==0 and sample['router']['unresolved_errors']==0
 for role in ('prefill','decode'):
  g=sample['servers'][role]['gauges'];assert all(v==0 for v in g.values()) and all(v is not None for v in g.values())
 for role,w in workers.items():
  files=list((p/'observer').glob(f'{role}-{w["pid"]}.jsonl'));assert len(files)==1
  snapshots=[json.loads(x) for x in files[0].open()];eligible=[x for x in snapshots if x['monotonic_ns']<=sample['monotonic_ns']];assert eligible
  s=max(eligible,key=lambda x:x['monotonic_ns']);age=(sample['monotonic_ns']-s['monotonic_ns'])/1e9;assert age<=1.5
  assert s['lock_acquired'] and s['queue_items']==s['buffer_bytes']==s['pipe_buffer_bytes']==s['signal_buffer_bytes']==0 and not any(s['active'].values()) and not any(s['pipe_active'].values())
  rows.append({'sample':sample['sample'],'role':role,'worker_pid':w['pid'],'snapshot_ns':s['monotonic_ns'],'snapshot_age_s':age,'signal_active':s['signal_active'],'signal_counts':s['signal_counts'],'data_counts':s['pipe_counts']})
for role in workers:
 group=[x for x in rows if x['role']==role];assert len(group)==4 and len({json.dumps(x['signal_counts'],sort_keys=True) for x in group})==1 and len({json.dumps(x['data_counts'],sort_keys=True) for x in group})==1
result={'status':'consistent_observation_not_readiness','warmups':4,'samples':rows,'limitations':['non-atomic sampled host state','no live PID-to-GPU UUID mapping was collected in this run','worker synchronization covers only prior work in its context','no crash or concurrent-new-request fencing test','no formal validation']}
(out/'audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
