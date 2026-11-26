import csv,json,pathlib,collections,statistics
root=pathlib.Path(__file__).parent;result={};seqs={};keys={}
for mode in ('original','corrected','dag'):
 p=root/mode;assert (p/'exit').read_text().strip()=='0';mfiles=list(p.glob('2026*/request_metrics.csv'));tfiles=list(p.glob('2026*/chrome_trace.json'));assert len(mfiles)==len(tfiles)==1
 metrics={int(x['Request Id']):x for x in csv.DictReader(mfiles[0].open())};assert set(metrics)==set(range(4))
 events=[e for e in json.loads(tfiles[0].read_text())['traceEvents'] if e.get('ph')=='X' and e.get('pid') in (0,1) and e.get('args',{}).get('request_ids')];events.sort(key=lambda x:x['ts']);hist=collections.Counter();seen={};decode=[];viol=[]
 for e in events:
  a=e['args'];ids=tuple(sorted(a['request_ids']));pairs=tuple(sorted(zip(a['request_ids'],a['num_tokens'])));k=(e['pid'],ids,tuple((i,hist[i]) for i in ids),pairs);assert k not in seen;seen[k]=e
  if e['pid']==1:
   decode.append(e)
   for rid in ids:
    early=float(metrics[int(rid)]['decode_arrived_at'])-e['ts']/1e6
    if early>1e-12:viol.append({'request_id':rid,'early_ms':early*1000})
    hist[rid]+=1
 keys[mode]=seen;seqs[mode]=decode;result[mode]={'requests':len(metrics),'decode_batches':len(decode),'early_memberships':viol,'first_batches':[{'start_ms':e['ts']/1000,'ids':e['args']['request_ids']} for e in decode[:4]]}
timeline=list((root/'dag').glob('2026*/timeline.csv'));assert len(timeline)==1
costs=collections.defaultdict(float)
for x in csv.DictReader(timeline[0].open()):costs[x['graph_id']]+=float(x['duration_s'])
for name in ('original','corrected'):
 a=keys['dag'];b=keys[name];common=set(a)&set(b);deltas=[]
 for k in common:
  e=a[k];prefix=f"replica{e['pid']}/stage0/batch{e['args']['batch_id']}/";graphs=[g for g in costs if g.startswith(prefix)];assert len(graphs)==1,(k,graphs)
  deltas.append(abs(costs[graphs[0]]-float(b[k]['dur'])/1e6))
 result[name+'_vs_dag']={'dag_batches':len(a),'baseline_batches':len(b),'matched':len(common),'dag_match_fraction':len(common)/len(a),'baseline_match_fraction':len(common)/len(b),'max_task_cost_difference_s':max(deltas) if deltas else None}
 a=seqs['dag'];b=seqs[name];i=next((i for i,(x,y) in enumerate(zip(a,b)) if sorted(x['args']['request_ids'])!=sorted(y['args']['request_ids'])),None)
 result[name+'_vs_dag']['first_positional_divergence']=None if i is None else {'index':i,'dag_ids':a[i]['args']['request_ids'],'baseline_ids':b[i]['args']['request_ids'],'dag_start_ms':a[i]['ts']/1000,'baseline_start_ms':b[i]['ts']/1000}
(root/'audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
