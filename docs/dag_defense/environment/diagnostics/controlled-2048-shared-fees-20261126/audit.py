import collections,csv,json,pathlib,hashlib
p=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/controlled-2048-shared-fees-20261126');out=pathlib.Path(__file__).parent;results={}
for case,count in [('one',1),('two_staggered',2),('two_simultaneous',2),('four_simultaneous',4)]:
 stats={};keys={};sums=collections.defaultdict(float)
 for mode in ('baseline','dag'):
  folder=p/case/mode;code=int((folder/'exit').read_text());result={'exit_code':code};stats[mode]=result
  if code:
   log=(folder/'process.log').read_text().splitlines();result['failure_tail']=log[-8:];continue
  events=[json.loads(x) for x in (folder/'first-token.jsonl').read_text().splitlines()];sub=[x for x in events if x['event']=='submit'];end=[x for x in events if x['event']=='complete'];assert len(sub)==len(end);assert sorted(r for x in sub for r in x['request_ids'])==list(map(str,range(count)))
  done={r:x['time_s'] for x in end for r in x['request_ids']};d=next(folder.glob('2026*'));metrics={str(int(x['Request Id'])):x for x in csv.DictReader((d/'request_metrics.csv').open())};assert set(metrics)==set(map(str,range(count)));assert all(float(m['request_num_prefill_tokens'])==2048 and float(m['request_num_decode_tokens'])==128 for m in metrics.values())
  for x in sub:
   assert all(float(metrics[r]['decode_arrived_at'])<=x['time_s']+1e-9 for r in x['request_ids']);assert abs(x['cost_s']-json.loads((p/'fee.json').read_text())['2048:'+str(len(x['request_ids']))])<1e-12
  trace=json.loads((d/'chrome_trace.json').read_text())['traceEvents'];ev=sorted([x for x in trace if x.get('ph')=='X' and x.get('pid') in (0,1) and x.get('args',{}).get('request_ids')],key=lambda x:x['ts']);history=collections.Counter();seen={};seq=[]
  for x in ev:
   a=x['args'];ids=tuple(sorted(a['request_ids']));pairs=tuple(sorted(zip(a['request_ids'],a['num_tokens'])));key=(x['pid'],ids,tuple((i,history[i]) for i in ids),pairs);assert key not in seen;seen[key]=x;seq.append(key)
   if x['pid']==1:
    for i in ids:assert x['ts']/1e6+1e-12>=done[str(i)]
    history.update(ids)
  assert all(history[i]==127 for i in range(count));keys[mode]=(seen,seq);result.update(batch_count=len(seen),groups=[x['request_ids'] for x in sub],decode_counts=dict(history),request_complete_s={r:float(m['completed_at']) for r,m in metrics.items()})
  if mode=='dag':
   for row in csv.DictReader((d/'timeline.csv').open()):sums[row['graph_id']]+=float(row['duration_s'])
 if len(keys)==2:
  a,ase=keys['baseline'];b,bse=keys['dag'];common=a.keys()&b.keys();deltas=[]
  for k in common:
   e=b[k];prefix=f"replica{e['pid']}/stage0/batch{e['args']['batch_id']}/";graphs=[x for x in sums if x.startswith(prefix)];assert len(graphs)==1;deltas.append(abs(float(a[k]['dur'])/1e6-sums[graphs[0]]))
  assert not deltas or max(deltas)<1e-9
  adec=[x for x in ase if x[0]==1];bdec=[x for x in bse if x[0]==1];diff=next(({'position':i,'baseline':str(a),'dag':str(b)} for i,(a,b) in enumerate(zip(adec,bdec)) if a!=b),None)
  stats['comparison']={'paired':len(common),'baseline_batches':len(a),'dag_batches':len(b),'max_paired_fee_difference_s':max(deltas) if deltas else None,'first_decode_difference':diff}
 results[case]=stats
(out/'audit.json').write_text(json.dumps(results,indent=2)+'\n');print(json.dumps(results,indent=2))
