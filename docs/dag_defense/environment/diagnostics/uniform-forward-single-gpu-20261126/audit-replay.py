import json,pathlib,csv,collections
base=pathlib.Path('/root/autodl-tmp/dag-handoff/runs');p=base/'uniform-forward-1024-four-replay-20261126';rows={}
for mode in ('baseline','dag'):
 assert (p/mode/'exit').read_text().strip()=='0';rows[mode]=[json.loads(x) for x in (p/mode/'forward.jsonl').read_text().splitlines()];assert len(rows[mode])==128
for a,b in zip(rows['baseline'],rows['dag']):assert (a['phase'],a['request_ids'],a['contexts'],a['lookup_key'],a['forward_ms'])==(b['phase'],b['request_ids'],b['contexts'],b['lookup_key'],b['forward_ms'])
assert len(rows['dag'][0]['request_ids'])==4 and all(len(r['request_ids'])==4 for r in rows['dag'])
f=next((p/'dag').glob('2026*/timeline.csv'));graphs=collections.defaultdict(list)
with f.open() as inp:
 for r in csv.DictReader(inp):
  if r['graph_id'].startswith('replica'):graphs[r['graph_id']].append(r)
assert len(graphs)==128
for g,tasks in graphs.items():
 assert sum(x['task_id']=='whole_forward' for x in tasks)==1 and not any(x['task_id'].startswith('layer') for x in tasks)
 batch=int(g.split('/batch')[1].split('/')[0]);assert abs(float(next(x['duration_s'] for x in tasks if x['task_id']=='whole_forward'))*1000-rows['dag'][batch]['forward_ms'])<1e-8
fail=base/'uniform-forward-2048-four-replay-v2-20261126'
for mode in ('baseline','dag'):
 assert (fail/mode/'exit').read_text().strip()!='0';log=(fail/mode/'process.log').read_text();assert 'CoverageError: unmeasured decode shape' in log and '2064' in log
result={'1024_four':{'baseline_batches':128,'dag_batches':128,'matched_forward_batches':128,'dag_graphs_with_one_forward_no_layers':128},'2048_four':{'status':'failed_missing_uniform_batch2_bin2064','baseline_exit':1,'dag_exit':1},'scope':'synthetic trace, adapted baseline, candidate costs; no formal validation'};pathlib.Path(__file__).with_name('replay-audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
