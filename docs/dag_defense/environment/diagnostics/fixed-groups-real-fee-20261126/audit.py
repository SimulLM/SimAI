import collections,csv,json,pathlib,hashlib
base=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/fixed-groups-real-fee-20261126/baseline');dag=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/real-first-token-2048-replay-20261126/dag');out=pathlib.Path(__file__).parent;keys={};results={};sums=collections.defaultdict(float)
for mode,p in [('fixed_baseline',base),('dag',dag)]:
 assert (p/'exit').read_text().strip()=='0';ev=[json.loads(x) for x in (p/'first-token.jsonl').read_text().splitlines()];sub=[x for x in ev if x['event']=='submit'];end=[x for x in ev if x['event']=='complete'];assert len(sub)==len(end)==3
 expected={('0',):.0011103435,('1','2'):.001115814,('3',):.0011103435};assert {tuple(x['request_ids']):x['cost_s'] for x in sub}==expected
 d=next(p.glob('2026*'));metrics={str(int(x['Request Id'])):x for x in csv.DictReader((d/'request_metrics.csv').open())};assert set(metrics)==set('0123')
 for e in sub:
  if mode=='fixed_baseline':assert all(float(metrics[x]['decode_arrived_at'])<=e['time_s']+1e-12 for x in e['request_ids'])
 complete={rid:x['time_s'] for x in end for rid in x['request_ids']};trace=json.loads((d/'chrome_trace.json').read_text())['traceEvents'];events=sorted([e for e in trace if e.get('ph')=='X' and e.get('pid') in (0,1) and e.get('args',{}).get('request_ids')],key=lambda e:e['ts']);hist=collections.Counter();seen={};sequence=[]
 for e in events:
  a=e['args'];ids=tuple(sorted(a['request_ids']));pairs=tuple(sorted(zip(a['request_ids'],a['num_tokens'])));k=(e['pid'],ids,tuple((i,hist[i]) for i in ids),pairs);assert k not in seen;seen[k]=e;sequence.append(k)
  if e['pid']==1:
   for i in ids:assert e['ts']/1e6+1e-12>=complete[str(i)]
   hist.update(ids)
 assert hist=={0:7,1:7,2:7,3:7};keys[mode]=(seen,sequence);results[mode]={'batch_count':len(seen),'groups':sub,'subsequent_decode_count':dict(hist)}
 if mode=='dag':
  for r in csv.DictReader((d/'timeline.csv').open()):sums[r['graph_id']]+=float(r['duration_s'])
a,ase=keys['fixed_baseline'];b,bse=keys['dag'];common=a.keys()&b.keys();deltas=[]
for k in common:
 e=b[k];prefix=f"replica{e['pid']}/stage0/batch{e['args']['batch_id']}/";g=[x for x in sums if x.startswith(prefix)];assert len(g)==1;deltas.append(abs(float(a[k]['dur'])/1e6-sums[g[0]]))
assert common and max(deltas)<1e-9
first=next(({'position':i,'baseline':str(x),'dag':str(y)} for i,(x,y) in enumerate(zip(ase,bse)) if x!=y),None)
adec=[x for x in ase if x[0]==1];bdec=[x for x in bse if x[0]==1];first_decode=next(({'position':i,'baseline':str(x),'dag':str(y)} for i,(x,y) in enumerate(zip(adec,bdec)) if x!=y),None)
sources=[pathlib.Path('/root/autodl-tmp/SimAI-baseline-kv-ready/vidur-alibabacloud/vidur/execution_time_predictor/sklearn_execution_time_predictor.py'),pathlib.Path('/root/autodl-tmp/SimAI-pristine-predictor-repro/vidur-alibabacloud/vidur/execution_time_predictor/sklearn_execution_time_predictor.py')];hs=[hashlib.sha256(x.read_bytes()).hexdigest() for x in sources];assert hs[0]==hs[1]
r={'predictor_sha256':hs[0],'first_decode_difference':first_decode,'status':'fixed_group_diagnostic_only','results':results,'matched_batches':len(common),'max_matched_cost_difference_s':max(deltas),'first_positional_difference':first,'limitations':['baseline modified, fixed groups chosen from instrumented real wave','not a natural-scheduling comparison or pristine baseline','groups not GPU resource-equivalent; baseline does not reserve decode GPU','profile includes selected wave and eight-output diagnostics','CPU/transfer overlap and response boundary not closed','not formal validation']};(out/'audit.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
