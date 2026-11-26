import collections,csv,json,pathlib,hashlib
root=pathlib.Path('/root/autodl-tmp/dag-handoff/runs');out={}
for case,n in [('simultaneous2',2),('simultaneous4',4)]:
 paths={'fixed_baseline':root/'batch-first-token-fixed-baseline-20261126'/case,'dag':root/'batch-first-token-common-predictor-20261126'/case};keys={};costs=collections.defaultdict(float)
 for mode,p in paths.items():
  assert (p/'exit').read_text().strip()=='0';events=[json.loads(x) for x in (p/'first-token.jsonl').read_text().splitlines()];assert len(events)==2 and events[0]['request_ids']==[str(i) for i in range(n)]
  r=next(p.glob('2026*'));metrics={int(x['Request Id']):x for x in csv.DictReader((r/'request_metrics.csv').open())};assert set(metrics)==set(range(n))
  assert all(float(m['decode_arrived_at'])<=events[0]['time_s'] for m in metrics.values())
  trace=json.loads((r/'chrome_trace.json').read_text());es=sorted([e for e in trace['traceEvents'] if e.get('ph')=='X' and e.get('pid') in (0,1) and e.get('args',{}).get('request_ids')],key=lambda x:x['ts']);history=collections.Counter();seen={}
  for e in es:
   a=e['args'];ids=tuple(sorted(a['request_ids']));pairs=tuple(sorted(zip(a['request_ids'],a['num_tokens'])));k=(e['pid'],ids,tuple((i,history[i]) for i in ids),pairs);assert k not in seen;seen[k]=e
   if e['pid']==1:
    assert e['ts']/1e6+1e-12>=events[1]['time_s']
    for rid in ids:history[rid]+=1
  assert all(history[i]==63 for i in range(n));keys[mode]=seen
  if mode=='dag':
   for x in csv.DictReader((r/'timeline.csv').open()):costs[x['graph_id']]+=float(x['duration_s'])
 a,b=keys['fixed_baseline'],keys['dag'];common=set(a)&set(b);delta=[]
 for k in common:
  e=b[k];prefix=f"replica{e['pid']}/stage0/batch{e['args']['batch_id']}/";graphs=[g for g in costs if g.startswith(prefix)];assert len(graphs)==1;delta.append(abs(costs[graphs[0]]-float(a[k]['dur'])/1e6))
 be=[json.loads(x) for x in (paths['fixed_baseline']/'first-token.jsonl').read_text().splitlines()];de=[json.loads(x) for x in (paths['dag']/'first-token.jsonl').read_text().splitlines()];assert be[0]['cost_s']==de[0]['cost_s']
 out[case]={'baseline_batches':len(a),'dag_batches':len(b),'matched_batches':len(common),'max_matched_batch_cost_diff_s':max(delta),'same_first_token_fee_s':be[0]['cost_s'],'baseline_first_token_start_s':be[0]['time_s'],'dag_first_token_start_s':de[0]['time_s'],'decode_steps_per_request':63,'baseline_modified_fixed_batch':True}
files=['/root/autodl-tmp/SimAI-baseline-kv-ready/vidur-alibabacloud/vidur/execution_time_predictor/sklearn_execution_time_predictor.py','/root/autodl-tmp/SimAI-pristine-predictor-repro/vidur-alibabacloud/vidur/execution_time_predictor/sklearn_execution_time_predictor.py'];hs=[hashlib.sha256(pathlib.Path(f).read_bytes()).hexdigest() for f in files];assert hs[0]==hs[1];out['predictor_sha256']=hs[0]
pathlib.Path(__file__).with_name('audit.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
negative=root/'batch-first-token-fixed-baseline-negative-20261126/simultaneous2';assert (negative/'exit').read_text().strip()=='1' and 'unexpected or duplicate fixed batch arrival' in (negative/'process.log').read_text();print('PASS mismatched fixed batch rejected')
