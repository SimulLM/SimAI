import collections,csv,json,pathlib,hashlib
p=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/paired-first-token-measured-20261126'); out=pathlib.Path(__file__).parent; keys={}; results={}; costs=collections.defaultdict(float)
for mode in ('baseline','dag'):
 f=p/mode;assert (f/'exit').read_text().strip()=='0';events=[json.loads(x) for x in (f/'first-token.jsonl').read_text().splitlines()];assert len(events)==2 and events[0]['event']=='submit' and events[1]['event']=='complete' and abs(events[0]['cost_s']-.000912567)<1e-12
 d=next(f.glob('2026*'));metrics={int(x['Request Id']):x for x in csv.DictReader((d/'request_metrics.csv').open())};assert set(metrics)=={0,1};assert all(float(x['decode_arrived_at'])<=events[0]['time_s'] for x in metrics.values())
 trace=json.loads((d/'chrome_trace.json').read_text()); es=sorted([e for e in trace['traceEvents'] if e.get('ph')=='X' and e.get('pid') in (0,1) and e.get('args',{}).get('request_ids')],key=lambda x:x['ts']);seen={};hist=collections.Counter()
 for e in es:
  a=e['args'];ids=tuple(sorted(a['request_ids']));pairs=tuple(sorted(zip(a['request_ids'],a['num_tokens'])));k=(e['pid'],ids,tuple((i,hist[i]) for i in ids),pairs);assert k not in seen;seen[k]=e
  if e['pid']==1:
   assert e['ts']/1e6+1e-12>=events[1]['time_s'];hist.update(ids)
 assert hist=={0:127,1:127};keys[mode]=seen;results[mode]={'batches':len(seen),'first_token_submit_s':events[0]['time_s'],'first_token_complete_s':events[1]['time_s'],'decode_count_per_request':dict(hist)}
 if mode=='dag':
  for x in csv.DictReader((d/'timeline.csv').open()):costs[x['graph_id']]+=float(x['duration_s'])
a,b=keys['baseline'],keys['dag'];common=a.keys() & b.keys();deltas=[]
for k in common:
 e=b[k];prefix=f"replica{e['pid']}/stage0/batch{e['args']['batch_id']}/";graphs=[g for g in costs if g.startswith(prefix)];assert len(graphs)==1;deltas.append(abs(costs[graphs[0]]-float(a[k]['dur'])/1e6))
assert len(common)>0 and max(deltas)<1e-9
sources=[pathlib.Path('/root/autodl-tmp/SimAI-baseline-kv-ready/vidur-alibabacloud/vidur/execution_time_predictor/sklearn_execution_time_predictor.py'),pathlib.Path('/root/autodl-tmp/SimAI-pristine-predictor-repro/vidur-alibabacloud/vidur/execution_time_predictor/sklearn_execution_time_predictor.py')];hs=[hashlib.sha256(f.read_bytes()).hexdigest() for f in sources];assert hs[0]==hs[1]
result={'input_tokens':1024,'output_tokens':128,'first_token_fee_s':.000912567,'paired_batches':len(common),'max_paired_batch_cost_diff_s':max(deltas),'results':results,'predictor_sha256':hs[0],'limitations':['fixed-batch diagnostic baseline modified','measured first token is synchronized host median from 30 waves, 7 warmup waves','transfer and other cost not established as physically non-overlapping','DAG resource demand assumed','not formal validation']};(out/'audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
