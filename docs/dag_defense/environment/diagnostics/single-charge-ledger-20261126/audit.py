import csv,glob,json,pathlib,collections,hashlib
out=pathlib.Path(__file__).parent
roots=glob.glob('/root/autodl-tmp/dag-handoff/runs/whole-forward-replay-20261126/dag/2026*');assert len(roots)==1
root=pathlib.Path(roots[0]);graphs=list((root/'graphs').glob('*.graph.json'));assert len(graphs)==66
records=[];kinds=collections.Counter();sums=collections.defaultdict(float)
for path in graphs:
 g=json.loads(path.read_text());tasks=g['tasks'];ids=[t['task_id'] for t in tasks]
 if any(i=='whole_forward' for i in ids):
  assert ids.count('whole_forward')==1 and not any(i.startswith('layer') for i in ids)
  kinds['decode']+=1;phase='decode'
 elif any(i.startswith('layer') for i in ids):
  assert len([i for i in ids if i.startswith('layer')])==96 and not any(i=='whole_forward' for i in ids)
  kinds['prefill']+=1;phase='prefill'
 elif 'transfer.0' in ids:
  assert ids.count('transfer.0')==1;kinds['transfer']+=1;phase='transfer'
 elif 'consumer.first_token' in ids:
  assert ids.count('consumer.first_token')==1;kinds['first_token']+=1;phase='first_token'
 else:raise ValueError('unknown graph '+str(path))
 for t in tasks:
  cost=t['cost']['duration_s']; sums[(phase,t['task_id'])]+=cost
  records.append({'graph':path.name,'phase':phase,'task_id':t['task_id'],'duration_s':cost,'cost_source':t['cost']['source'],'components':json.dumps(t.get('metadata',{}).get('components',{}),sort_keys=True)})
assert kinds=={'prefill':1,'decode':63,'transfer':1,'first_token':1},kinds
assert abs(sums[('transfer','transfer.0')]-0.012557707323809522)<1e-12
assert abs(sums[('first_token','consumer.first_token')]-0.000875779)<1e-12
with (out/'tasks.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=records[0]);w.writeheader();w.writerows(sorted(records,key=lambda x:(x['phase'],x['graph'],x['task_id'])))
summary={'graphs':dict(kinds),'task_count':len(records),'costs': [{'phase':k[0],'task_id':k[1],'sum_s':v} for k,v in sorted(sums.items()) if k[1] in ('transfer.0','consumer.first_token','whole_forward','cpu.prepare','cpu.finish')], 'scope':'single 512/64 diagnostic replay; structural nonduplication only','limitations':['measurement scopes and GPU/host overlap not fully proven','sync receive and first-token fees perturb execution','not applicable to concurrent shape or pristine original','not a freeze or accuracy claim']}
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
