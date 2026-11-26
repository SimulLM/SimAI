import collections,csv,json,pathlib
base=pathlib.Path('/root/autodl-tmp/dag-handoff/runs');results={}
for name,length,count in [('strict-forward-1024-final-20261126',1024,1),('strict-forward-2048-final-20261126',2048,1),('strict-forward-two-final-20261126',1024,2)]:
 p=base/name;values={}
 for mode in ('baseline','dag'):
  assert (p/mode/'exit').read_text().strip()=='0';rows=[json.loads(x) for x in (p/mode/'forward.jsonl').read_text().splitlines()];assert len(rows)==128
  assert rows[0]['phase']=='prefill' and len(rows[0]['request_ids'])==count and all(x['phase']=='decode' for x in rows[1:])
  assert [int(x['contexts'][0]) for x in rows[1:]]==list(range(length+1,length+128));values[mode]=rows
 for a,b in zip(values['baseline'],values['dag']):
  assert a['phase']==b['phase'] and a['contexts']==b['contexts'] and a['request_ids']==b['request_ids'] and a['lookup_key']==b['lookup_key'] and abs(a['forward_ms']-b['forward_ms'])<1e-9
 f=next((p/'dag').glob('2026*/timeline.csv'))
 with f.open() as file:timeline=list(csv.DictReader(file))
 graphs=collections.defaultdict(list)
 for row in timeline:
  if row['graph_id'].startswith('replica'):graphs[row['graph_id']].append(row)
 assert len(graphs)==128
 durations={}
 for graph,tasks in graphs.items():
  assert sum(x['task_id']=='whole_forward' for x in tasks)==1 and not any(x['task_id'].startswith('layer') for x in tasks)
  durations[int(graph.split('/batch')[1].split('/')[0])]=float(next(x['duration_s'] for x in tasks if x['task_id']=='whole_forward'))*1000
 for x in values['dag']:assert abs(x['forward_ms']-durations[x['batch_id']])<1e-8
 results[name]={'requests':count,'prefill_batches':1,'decode_batches':127,'matched_forward_batches':128,'dag_batches':128,'baseline_batches':128,'prefill_forward_ms':values['dag'][0]['forward_ms'],'decode_forward_sum_ms':sum(x['forward_ms'] for x in values['dag'][1:])}
p=base/'strict-forward-four-final-20261126';failures={}
for mode in ('baseline','dag'):
 assert (p/mode/'exit').read_text().strip()!='0';log=(p/mode/'process.log').read_text();assert 'CoverageError: unmeasured decode shape' in log and '1040' in log;failures[mode]='missing 1024 input, batch 4, bin 1040, uniform context'
results['strict-forward-four-final-20261126']={'requests':4,'failed_as_expected':failures}
output=pathlib.Path(__file__).with_name('audit.json');output.write_text(json.dumps(results,indent=2)+'\n');print(json.dumps(results,indent=2))
