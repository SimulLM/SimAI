import collections,csv,hashlib,json,pathlib,sys
root=pathlib.Path('/root/autodl-tmp/SimAI-handoff'); sys.path.insert(0,str(root))
from scripts.dag_defense.forward_diagnostic.lookup import ForwardLookup,CoverageError
base=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/common-cost-matrix-v2-20261126')
pref=root/'docs/dag_defense/environment/diagnostics/pd-eager-profile-20261126/candidate/forward-cost.csv'; dec=root/'docs/dag_defense/environment/diagnostics/forward-coverage-refresh-20261126/strict-forward-context-bins.csv'
lookup=ForwardLookup(pref,dec); cases=[]; records=[]
for case in sorted(p for p in base.iterdir() if p.is_dir() and '-' in p.name):
 length,n=map(int,case.name.split('-')); trace=case/'requests.csv'
 for role in ('baseline','dag'):
  tracefiles=list((case/role).glob('*/chrome_trace.json')); assert len(tracefiles)==1
  file=tracefiles[0]; events=json.loads(file.read_text())['traceEvents']; seen=collections.Counter(); counts=collections.Counter()
  for ev in sorted(events,key=lambda e:e.get('ts',0)):
   a=ev.get('args',{}); ids=sorted(a.get('request_ids',[])); pid=ev.get('pid'); tokens=a.get('num_tokens',[])
   if ev.get('ph')!='X' or not ids or pid not in (0,1):continue
   phase='prefill' if pid==0 else 'decode'; contexts=[0]*len(ids) if pid==0 else [length+1+seen[r] for r in ids]
   try: key,_=lookup.get(phase,[length]*len(ids),contexts,tokens); status='covered'; detail=str(key)
   except CoverageError as e: status='missing'; detail=str(e)
   counts[(phase,status)]+=1
   records.append({'case':case.name,'role':role,'phase':phase,'batch_id':a['batch_id'],'request_ids':','.join(map(str,ids)),'contexts':','.join(map(str,contexts)),'tokens':','.join(map(str,tokens)),'status':status,'lookup':detail})
   if pid==1:
    for rid in ids:seen[rid]+=1
  cases.append({'case':case.name,'role':role,'synthetic_request_csv_sha256':hashlib.sha256(trace.read_bytes()).hexdigest(),'chrome_trace_sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'counts':{f'{p}_{s}':v for (p,s),v in sorted(counts.items())},'decode_steps_per_request':dict(sorted(seen.items()))})
out=pathlib.Path(__file__).parent
with (out/'batches.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=records[0].keys());w.writeheader();w.writerows(records)
(out/'summary.json').write_text(json.dumps({'scope':'previous synthetic simultaneous wave replays; candidate fees and schedules, not validation or hardware','context_assumption':'input length + 1 + number of previously traced consumer batches for each request; inspect against strict adapter semantics','cases':cases,'lookup_source_sha256':lookup.hashes},indent=2)+'\n')
print(json.dumps(cases,indent=2))
# Check reconstruction against adapter-recorded contexts on independent completed traces.
checks=[]
for name,length in [('strict-forward-1024-final-20261126',1024),('strict-forward-2048-final-20261126',2048),('strict-forward-two-final-20261126',1024)]:
 for role in ('baseline','dag'):
  folder=base.parent/name/role; raw=(folder/'forward.jsonl').read_bytes(); observed=[json.loads(x) for x in raw.splitlines()]; source=next(folder.glob('*/chrome_trace.json')); events=json.loads(source.read_text())['traceEvents']; by_batch={e['args']['batch_id']:e['args']['request_ids'] for e in events if e.get('ph')=='X' and e.get('pid') in (0,1) and e.get('args',{}).get('request_ids')}; seen=collections.Counter(); mismatch=[]
  for row in observed:
   ids=by_batch[row['batch_id']]; expected=[length+1+seen[i] for i in ids] if row['phase']=='decode' else [0]*len(ids)
   if dict(zip(ids,expected))!=dict(zip(row['request_ids'],row['contexts'])):mismatch.append(row['batch_id'])
   if row['phase']=='decode':seen.update(ids)
  assert len(observed)==128 and not mismatch
  checks.append({'run':name,'role':role,'batches':len(observed),'mismatch_count':len(mismatch),'forward_sha256':hashlib.sha256(raw).hexdigest(),'chrome_sha256':hashlib.sha256(source.read_bytes()).hexdigest()})
summary=json.loads((out/'summary.json').read_text());summary['context_reconstruction_checks']=checks;(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
