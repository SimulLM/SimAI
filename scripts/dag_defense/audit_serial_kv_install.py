"""Audit same-step install bounds from intrusive serial PD diagnostics."""
import collections,csv,json,math,pathlib,statistics,sys
root=pathlib.Path(sys.argv[1]);out=pathlib.Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=False)
assert (root/'exit').read_text().strip()=='0'
requests=[json.loads(x) for x in (root/'client.jsonl').read_text().splitlines()];assert len(requests)==120
router=collections.defaultdict(dict)
for line in (root/'service/router-events.jsonl').read_text().splitlines():
 e=json.loads(line);assert e['event'] not in router[e['request_id']];router[e['request_id']][e['event']]=e
worker=collections.defaultdict(list)
for file in (root/'service/events').glob('*.jsonl'):
 for line in file.read_text().splitlines():
  e=json.loads(line)
  if e.get('role')=='consumer' and e.get('step_id'):
   for group in e.get('groups',[]):worker[(group['request_id'],e['step_id'])].append(e)
rows=[]
for r in requests:
 assert r['status']==200 and r['done'] and r['usage']['prompt_tokens']==r['length'] and r['usage']['completion_tokens']==8
 ev=router[r['router_id']];rid=ev['decode_mapping']['backend_request_id']+'-0';assert rid==r['backend_id']+'-0'
 candidates=[v for (request,step),v in worker.items() if request==rid and any(x['event']=='kv_install_sync_complete' for x in v)];assert len(candidates)==1;v=candidates[0]
 def times(name):return sorted(x['timestamp_ns'] for x in v if x['event']==name)
 starts=times('kv_install_api_start');returns=times('kv_install_api_return');syncstart=times('kv_install_sync_start');syncend=times('kv_install_sync_complete')
 assert len(starts)==len(returns)==32 and len(syncstart)==len(syncend)==1 and all(a<=b for a,b in zip(starts,returns)) and starts[0]<=returns[-1]<=syncstart[0]<=syncend[0]
 rows.append({'length':r['length'],'wave':r['wave'],'warmup':r['warmup'],'router_id':r['router_id'],'decode_id':rid,'install_first_api_ns':starts[0],'install_last_api_return_ns':returns[-1],'post_recv_sync_start_ns':syncstart[0],'post_recv_sync_end_ns':syncend[0],'first_api_to_sync_ms':(syncend[0]-starts[0])/1e6,'last_return_to_sync_ms':(syncend[0]-returns[-1])/1e6})
with (out/'samples.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
groups=[]
for length in (512,1024,2048):
 group=[r for r in rows if r['length']==length];warm=[x for x in group if x['warmup']];measured=[x for x in group if not x['warmup']];assert len(warm)==10 and len(measured)==30
 metrics={}
 for key in ('first_api_to_sync_ms','last_return_to_sync_ms'):
  vals=sorted(x[key] for x in measured);metrics[key]={'median':statistics.median(vals),'min':vals[0],'max':vals[-1],'p95_nearest_rank':vals[math.ceil(.95*len(vals))-1]}
 groups.append({'length':length,'warmups':len(warm),'measured':len(measured),'metrics':metrics})
summary={'status':'synchronized_install_diagnostic_not_frozen','groups':groups,'limitations':['Interval from first install API start to device synchronization includes enqueue, concurrent GPU work, host overhead and waiting; it is not an isolated non-overlap fee','Last API return to device sync is only a bound on outstanding work, not total installation cost','Per-tensor transport synchronizations perturb scheduling','Serial only, output length 8, no formal validation or CPU/GPU overlap contract']}
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
