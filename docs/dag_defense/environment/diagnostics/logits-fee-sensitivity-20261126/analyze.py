import collections,csv,json,math,pathlib,statistics,hashlib
src=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/accounting-reanalysis-20261126');out=pathlib.Path(__file__).parent
requests=[json.loads(x) for x in (src/'coverage-retry/requests.jsonl').read_text().splitlines()];selected={x['backend_request_id']+'-0':x for x in requests if x['batch']==1 and not x['warmup'] and x['status']==200};assert len(selected)==30
byid=collections.defaultdict(list)
for line in (src/'compute-events-83657.jsonl').open():
 e=json.loads(line)
 if e.get('event')!='model_step':continue
 for g in e.get('groups',[]):
  if g['request_id'] in selected and not g['is_prompt']:
   assert len(e['request_ids_to_seq_ids'])==1 and 'full_model_forward' in e['gpu_event_ms']
   byid[g['request_id']].append(e)
assert set(byid)==set(selected) and all(len(v)==63 for v in byid.values())
rows=[]
for rid,es in sorted(byid.items()):
 v=[x['gpu_event_ms']['logits_gpu'] for x in es];rows.append({'request_id':rid,'wave':selected[rid]['wave'],'steps':len(v),'median_logits_ms':statistics.median(v),'min_logits_ms':min(v),'max_logits_ms':max(v)})
with (out/'request-medians.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
vals=sorted(x['median_logits_ms'] for x in rows);result={'requests':len(rows),'steps_each':63,'median_of_request_medians_ms':statistics.median(vals),'min_ms':min(vals),'max_ms':max(vals),'p95_ms':vals[math.ceil(.95*len(vals))-1],'source_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (src/'coverage-retry/requests.jsonl',src/'compute-events-83657.jsonl')},'limitations':['one session and fixed input; requests not independent service restarts','GPU event interval may include idle gaps; instrumentation perturbs timing','does not establish additive wall time or concurrent coverage','not formal validation or fitted E2E correction']}
(out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
