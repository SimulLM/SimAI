import collections,csv,json,pathlib
base=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/real-first-token-2048-replay-20261126');mapping=json.loads((base/'input-mapping.json').read_text())['mapping'];lookup={x['backend_id']+'-0':x['sim_id'] for x in mapping};src=pathlib.Path('/root/autodl-tmp/SimAI-handoff/docs/dag_defense/environment/diagnostics/first-token-batch-accounting-20261126/distinct-steps.jsonl');real=[]
for x in map(json.loads,src.open()):
 if all(rid in lookup for rid in x['mapped_ids']):real.append(tuple(sorted(lookup[rid] for rid in x['mapped_ids'])))
results={};keys={};seq={};dagcost=collections.defaultdict(float)
for mode in ('original','dag'):
 p=base/mode;assert (p/'exit').read_text().strip()=='0';root=next(p.glob('2026*'));metrics={int(x['Request Id']):x for x in csv.DictReader((root/'request_metrics.csv').open())};assert set(metrics)==set(range(4))
 es=sorted((e for e in json.loads((root/'chrome_trace.json').read_text())['traceEvents'] if e.get('ph')=='X' and e.get('pid') in (0,1) and e.get('args',{}).get('request_ids')),key=lambda e:e['ts']);hist=collections.Counter();seen={};early=[];decode=[]
 for e in es:
  a=e['args'];ids=tuple(sorted(a['request_ids']));pairs=tuple(sorted(zip(a['request_ids'],a['num_tokens'])));k=(e['pid'],ids,tuple((i,hist[i]) for i in ids),pairs);assert k not in seen;seen[k]=e
  if e['pid']==1:
   decode.append(e)
   for rid in ids:
    delta=float(metrics[rid]['decode_arrived_at'])-e['ts']/1e6
    if delta>1e-12:early.append({'request_id':rid,'early_ms':delta*1000})
    hist[rid]+=1
 assert hist=={i:7 for i in range(4)};keys[mode]=seen;seq[mode]=decode;results[mode]={'batches':len(seen),'decode_batches':len(decode),'early_memberships':early}
 if mode=='dag':
  for x in csv.DictReader((root/'timeline.csv').open()):dagcost[x['graph_id']]+=float(x['duration_s'])
  events=[json.loads(x) for x in (p/'first-token.jsonl').read_text().splitlines()];assert len(events)%2==0;groups=[];tr={int(x['request_id']):x for x in csv.DictReader((root/'pd-transfers.csv').open())}
  for a,b in zip(events[::2],events[1::2]):
   assert a['event']=='submit' and b['event']=='complete' and a['request_ids']==b['request_ids'];g=tuple(sorted(map(int,a['request_ids'])));groups.append(g)
   for rid in g:assert float(tr[rid]['kv_ready_at_s'])<=a['time_s']<=b['time_s']<=float(tr[rid]['first_decode_start_s']) and all(int(tr[rid][k])==0 for k in ('source_reservations','destination_reservations','pins'))
common=keys['original'].keys()&keys['dag'].keys();deltas=[]
for k in common:
 e=keys['dag'][k];prefix=f"replica{e['pid']}/stage0/batch{e['args']['batch_id']}/";gg=[g for g in dagcost if g.startswith(prefix)];assert len(gg)==1;deltas.append(abs(dagcost[gg[0]]-float(keys['original'][k]['dur'])/1e6))
i=next((i for i,(a,b) in enumerate(zip(seq['original'],seq['dag'])) if sorted(a['args']['request_ids'])!=sorted(b['args']['request_ids'])),None)
results.update({'real_first_token_groups':real,'dag_first_token_groups':groups,'paired_first_token_groups':len(set(real)&set(groups)),'real_first_token_group_count':len(real),'dag_first_token_group_count':len(groups),'paired_compute_batches':len(common),'max_paired_compute_cost_diff_s':max(deltas) if deltas else None,'first_decode_membership_difference':None if i is None else {'index':i,'original_ids':seq['original'][i]['args']['request_ids'],'dag_ids':seq['dag'][i]['args']['request_ids']},'limitations':['one 8-output instrumented wave, not validation or holdout','original lacks consumer first-token task; no full same-fee comparison','same capture contributed fee medians','arrival replay does not make simulated transfer model physical','paired compute cost excludes first-token and resource waits']})
pathlib.Path(__file__).with_name('audit.json').write_text(json.dumps(results,indent=2)+'\n');print(json.dumps(results,indent=2))
