import collections,csv,hashlib,json,pathlib,subprocess
root=pathlib.Path('/root/autodl-tmp/dag-handoff/runs');orig=root/'controlled-2048-pristine-20261126';prior=root/'controlled-2048-shared-fees-20261126';out=pathlib.Path(__file__).parent;baseline=pathlib.Path('/root/autodl-tmp/SimAI-pristine-baseline')
assert subprocess.check_output(['git','-C',str(baseline),'rev-parse','HEAD'],text=True).strip()=='cef83f9ddd96540e3e9f48934f11335d52d54fce';assert subprocess.run(['git','-C',str(baseline),'diff','--quiet']).returncode==0 and subprocess.run(['git','-C',str(baseline),'diff','--cached','--quiet']).returncode==0
results={}
for case,count in [('one',1),('two_staggered',2),('two_simultaneous',2),('four_simultaneous',4)]:
 paths={'pristine':orig/case,'fixed_baseline':prior/case/'baseline','dag':prior/case/'dag'};histories={};steps={};stats={};task_costs=collections.defaultdict(float)
 for mode,p in paths.items():
  assert (p/'exit').read_text().strip()=='0';d=next(p.glob('2026*'));metrics={int(x['Request Id']):x for x in csv.DictReader((d/'request_metrics.csv').open())};assert set(metrics)==set(range(count));assert all(float(x['request_num_prefill_tokens'])==2048 and float(x['request_num_decode_tokens'])==128 for x in metrics.values())
  events=json.loads((d/'chrome_trace.json').read_text())['traceEvents'];events=sorted([e for e in events if e.get('ph')=='X' and e.get('pid') in (0,1) and e.get('args',{}).get('request_ids')],key=lambda e:e['ts']);h=collections.Counter();seen={};seq=[];early=[]
  for e in events:
   a=e['args'];ids=tuple(sorted(a['request_ids']));pairs=tuple(sorted(zip(a['request_ids'],a['num_tokens'])));k=(e['pid'],ids,tuple((i,h[i]) for i in ids),pairs);assert k not in seen;seen[k]=e
   if e['pid']==1:
    seq.append({'key':str(k),'start_s':e['ts']/1e6,'ids':ids})
    for rid in ids:
     ready=float(metrics[rid]['decode_arrived_at']);start=e['ts']/1e6
     if start+1e-9<ready:early.append({'request_id':rid,'batch_id':a['batch_id'],'start_s':start,'modeled_ready_s':ready,'early_ms':(ready-start)*1000})
    h.update(ids)
  assert all(h[i]==127 for i in range(count));histories[mode]=seen;steps[mode]=seq;stats[mode]={'batches':len(seen),'early_decode_memberships':early,'decode_steps':dict(h),'request_complete_s':{str(i):float(x['completed_at']) for i,x in metrics.items()}}
  if mode=='dag':
   for row in csv.DictReader((d/'timeline.csv').open()):task_costs[row['graph_id']]+=float(row['duration_s'])
 for mode in ('pristine','fixed_baseline'):
  a=histories[mode];b=histories['dag'];common=a.keys()&b.keys();diff=[]
  for k in common:
   e=b[k];prefix=f"replica{e['pid']}/stage0/batch{e['args']['batch_id']}/";g=[x for x in task_costs if x.startswith(prefix)];assert len(g)==1;diff.append(abs(float(a[k]['dur'])/1e6-task_costs[g[0]]))
  assert not diff or max(diff)<1e-9
  first=next(({'position':i,'other':x,'dag':y} for i,(x,y) in enumerate(zip(steps[mode],steps['dag'])) if x['key']!=y['key']),None)
  stats[mode+'_vs_dag']={'paired_batches':len(common),'other_batches':len(a),'dag_batches':len(b),'max_paired_model_cost_diff_s':max(diff) if diff else None,'first_decode_difference':first}
 assert not stats['fixed_baseline']['early_decode_memberships'] and not stats['dag']['early_decode_memberships'];results[case]=stats
res={'status':'diagnostic_not_formal','baseline_commit':'cef83f9ddd96540e3e9f48934f11335d52d54fce','trace_sha256':{case:hashlib.sha256((prior/case/'trace.csv').read_bytes()).hexdigest() for case in results},'cases':results,'limitations':['synthetic arrivals','pristine lacks consumer first-token stage and cannot be considered same total fees','modified fixed baseline is diagnostic only','transfer modeled readiness is not physical KVReady','fee candidates not frozen, not formal validation']};(out/'audit.json').write_text(json.dumps(res,indent=2)+'\n');print(json.dumps(res,indent=2))
