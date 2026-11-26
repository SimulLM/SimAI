import collections,csv,json,pathlib,hashlib
root=pathlib.Path('/root/autodl-tmp/dag-handoff/runs');p=root/'dynamic-calibration-512-20261126';pristine=root/'pristine-real-arrival-20261126';out=pathlib.Path(__file__).parent;result={}
for case in ('serial-0','concurrent-0'):
 paths={'pristine':pristine/case/'baseline','dynamic':p/case/'baseline','dag':p/case/'dag'};mode_result={};keys={};decode={};costs=collections.defaultdict(float)
 for mode,folder in paths.items():
  exitcode=int((folder/'exit').read_text());record={'exit_code':exitcode};mode_result[mode]=record
  if exitcode:
   record['failure_tail']=(folder/'process.log').read_text().splitlines()[-8:];continue
  d=next(folder.glob('2026*'));metrics={int(x['Request Id']):x for x in csv.DictReader((d/'request_metrics.csv').open())};assert len(metrics)==32 and all(float(x['request_num_prefill_tokens'])==512 and float(x['request_num_decode_tokens'])==64 for x in metrics.values())
  ev=json.loads((d/'chrome_trace.json').read_text())['traceEvents'];events=sorted([e for e in ev if e.get('ph')=='X' and e.get('pid') in (0,1) and e.get('args',{}).get('request_ids')],key=lambda x:x['ts']);h=collections.Counter();seen={};order=[];early=[]
  for e in events:
   a=e['args'];ids=tuple(sorted(a['request_ids']));pairs=tuple(sorted(zip(a['request_ids'],a['num_tokens'])));key=(e['pid'],ids,tuple((i,h[i]) for i in ids),pairs);assert key not in seen;seen[key]=e
   if e['pid']==1:
    order.append(str(key))
    for i in ids:
     ready=float(metrics[i]['decode_arrived_at']);now=e['ts']/1e6
     if now+1e-9<ready:early.append({'request_id':i,'batch_id':a['batch_id'],'early_ms':(ready-now)*1000})
    h.update(ids)
  assert len(h)==32 and all(h[i]==63 for i in metrics);keys[mode]=seen;decode[mode]=order;record.update(requests=32,batches=len(seen),early_memberships=len(early),early_examples=early[:8],decode_steps_per_request=63)
  if mode!='pristine':
   rows=[json.loads(x) for x in (folder/'first-token.jsonl').read_text().splitlines()];sub=[x for x in rows if x['event']=='submit'];end=[x for x in rows if x['event']=='complete'];assert len(sub)==len(end) and sum(len(x['request_ids']) for x in sub)==32
   done={rid:x['time_s'] for x in end for rid in x['request_ids']};assert set(done)==set(map(str,metrics))
   for task in sub:
    assert all(float(metrics[int(rid)]['decode_arrived_at'])<=task['time_s']+1e-9 for rid in task['request_ids'])
    assert task['cost_s']==json.loads((p/'fee.json').read_text())['512:'+str(len(task['request_ids']))]
   for e in events:
    if e['pid']==1:
     for rid in e['args']['request_ids']:assert e['ts']/1e6+1e-9>=done[str(rid)]
   record['first_token_groups']=dict(collections.Counter(str(len(x['request_ids'])) for x in sub));record['first_token_task_count']=len(sub)
   assert not early
  if mode=='dag':
   for x in csv.DictReader((d/'timeline.csv').open()):costs[x['graph_id']]+=float(x['duration_s'])
 if 'dag' in keys:
  for mode in ('pristine','dynamic'):
   if mode not in keys:continue
   a=keys[mode];b=keys['dag'];common=a.keys()&b.keys();diff=[]
   for k in common:
    e=b[k];prefix=f"replica{e['pid']}/stage0/batch{e['args']['batch_id']}/";g=[x for x in costs if x.startswith(prefix)];assert len(g)==1;diff.append(abs(float(a[k]['dur'])/1e6-costs[g[0]]))
   assert not diff or max(diff)<1e-9
   first=next(({'position':i,'other':x,'dag':y} for i,(x,y) in enumerate(zip(decode[mode],decode['dag'])) if x!=y),None)
   mode_result[mode+'_vs_dag']={'paired_batches':len(common),'other_batches':len(a),'dag_batches':len(b),'max_paired_fee_difference_s':max(diff) if diff else None,'first_decode_difference':first}
 result[case]=mode_result
(out/'audit.json').write_text(json.dumps({'cases':result,'scope':'real calibration router arrivals; diagnostic modified baseline and DAG; not formal validation','limitations':['pristine lacks consumer first-token task','8-output synchronized first-token fees applied to 64-output replay','no proof of GPU occupancy or real connector overlap','natural schedule comparison is calibration only']},indent=2)+'\n');print(json.dumps(result,indent=2))
