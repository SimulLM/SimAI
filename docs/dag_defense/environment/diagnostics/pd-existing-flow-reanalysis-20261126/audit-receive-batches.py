"""Audit measured requests against preserved consumer model-step events."""
import collections,csv,json,pathlib,tarfile
root=pathlib.Path(__file__).resolve().parent; source=root.parent/'pd-flow-boundary-20261126'
rows=[r for r in csv.DictReader((source/'derived-boundaries.csv').open()) if r['warmup'].lower()=='false'];targets={r['decode_id']+'-0' for r in rows}
counts=collections.Counter();hits=collections.Counter();events=[]
with tarfile.open(source/'raw.tar.gz') as archive:
 for line in archive.extractfile('compute-events-85025.jsonl'):
  e=json.loads(line)
  if e.get('event')!='model_step':continue
  groups=e.get('groups',[]); ids=[g['request_id'] for g in groups]; selected=set(ids)&targets
  if not selected or not e.get('host_intervals',{}).get('recv_kv_caches_and_hidden_states'):continue
  counts[(len(groups),sum(not g['is_prompt'] for g in groups))]+=1
  hits.update(selected);events.append(e)
if set(hits)!=targets or any(n!=1 for n in hits.values()):raise ValueError('missing or duplicate measured receive step')
result={'scope':'Instrumented 8-token diagnostic; observed receive steps only; step data from pid 85025. This is not proof of general vLLM behavior.','requests':len(targets),'receive_steps':len(events),'distribution':[{'step_groups':n,'decode_groups':d,'steps':c} for (n,d),c in sorted(counts.items())]}
(root/'receive-batches.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
