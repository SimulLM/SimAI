import collections,csv,json,pathlib
base=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/real-first-token-fee-replay-20261126');p=base/'dag';assert (p/'exit').read_text().strip()=='0'
mapping=json.loads((base/'input-mapping.json').read_text())['mapping'];lookup={x['backend_id']+'-0':x['sim_id'] for x in mapping};assert len(lookup)==4
source=pathlib.Path('/root/autodl-tmp/SimAI-handoff/docs/dag_defense/environment/diagnostics/first-token-batch-accounting-20261126/distinct-steps.jsonl');real=[]
for row in map(json.loads,source.open()):
 if all(rid in lookup for rid in row['mapped_ids']):real.append(tuple(sorted(lookup[rid] for rid in row['mapped_ids'])))
assert sorted(real)==[(0,),(1,2,3)]
events=[json.loads(x) for x in (p/'first-token.jsonl').read_text().splitlines()];assert len(events)==4;groups=[]
for a,b in zip(events[::2],events[1::2]):
 assert a['event']=='submit' and b['event']=='complete' and a['request_ids']==b['request_ids'];groups.append(tuple(sorted(int(x) for x in a['request_ids'])))
assert sorted(groups)==sorted(real)
r=next(p.glob('2026*'));transfers={int(x['request_id']):x for x in csv.DictReader((r/'pd-transfers.csv').open())};assert set(transfers)==set(range(4))
for a,b in zip(events[::2],events[1::2]):
 for rid in map(int,a['request_ids']):
  x=transfers[rid];assert x['state']=='COMPLETED' and float(x['kv_ready_at_s'])<=a['time_s']<=b['time_s']<=float(x['first_decode_start_s']);assert all(int(x[k])==0 for k in ('source_reservations','destination_reservations','pins'))
trace=json.loads((r/'chrome_trace.json').read_text());history=collections.Counter()
for e in trace['traceEvents']:
 if e.get('ph')=='X' and e.get('pid')==1:
  for rid in e.get('args',{}).get('request_ids',[]):history[rid]+=1
assert history=={0:7,1:7,2:7,3:7}
result={'status':'diagnostic_only','input_tokens':1024,'output_tokens':8,'requests':4,'real_first_token_groups':real,'dag_first_token_groups':groups,'paired_groups':len(set(real)&set(groups)),'real_group_count':len(real),'dag_group_count':len(groups),'decode_steps_per_request':7,'fees_s':json.loads((base/'fee.json').read_text()),'limitations':['same instrumented capture supplies arrivals and fee samples; not holdout','DAG-only; no same-fee baseline','synchronized host first-token interval is not proven equivalent to GPU occupancy or additive','communication and compute fees are candidate models; not certified by this audit','real service and DAG timings differ; group match does not prove timing parity','not formal validation']};pathlib.Path(__file__).with_name('audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
