import json,statistics,csv,hashlib
from pathlib import Path
p=Path(__file__).parent
requests=[json.loads(x) for x in (p/'coverage-retry/requests.jsonl').read_text().splitlines()]
r=next(x for x in requests if x['batch']==1 and not x['warmup'] and x['status']==200)
rid=r['backend_request_id']+'-0'
steps=[]
for line in (p/'compute-events-83657.jsonl').open():
 e=json.loads(line)
 if e.get('event')=='model_step' and rid in e.get('request_ids_to_seq_ids',{}):steps.append(e)
steps.sort(key=lambda e:e['host_start_ns'])
assert len(steps)==64 and all(len(e['request_ids_to_seq_ids'])==1 for e in steps)
assert [bool(next(g['is_prompt'] for g in e['groups'] if g['request_id']==rid)) for e in steps]==[True]+[False]*63
rows=[]
for i,e in enumerate(steps):
 t=e['gpu_event_ms']; h=e['host_intervals']; assert 'logits_gpu' in t and 'sampler_gpu' in t
 assert h['logits'][0]<=h['logits'][1]<=h['sampler'][0]<=h['sampler'][1]<=e['host_after_sync_ns']
 rows.append(dict(step=i,phase='kv_bypass' if i==0 else 'decode',context=e['seq_lens'][0],host_start_ns=e['host_start_ns'],logits_host_start_ns=h['logits'][0],logits_host_end_ns=h['logits'][1],sampler_host_start_ns=h['sampler'][0],sampler_host_end_ns=h['sampler'][1],host_after_sync_ns=e['host_after_sync_ns'],full_forward_gpu_ms=t.get('full_model_forward'),logits_gpu_ms=t['logits_gpu'],sampler_gpu_ms=t['sampler_gpu'],sampler_host_ms=(h['sampler'][1]-h['sampler'][0])/1e6))
out=p/'paired-steps.csv'
with out.open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
dec=rows[1:]
summary={'request_id':rid,'wave':r['wave'],'input_tokens':r['usage']['prompt_tokens'],'output_tokens':r['usage']['completion_tokens'],'finish_reason':r['finish_reason'],'first':rows[0],'decode_steps':len(dec),'decode_median_ms':{k:statistics.median(x[k] for x in dec) for k in ['full_forward_gpu_ms','logits_gpu_ms','sampler_gpu_ms','sampler_host_ms']},'limitations':['One instrumented serial request, steps are correlated.','GPU event elapsed intervals can include device idle gaps; hooks and synchronization perturb execution.','Host sampler call may overlap queued device work; GPU sampler is not added to host sampler.','No timing is fitted to E2E; no uninstrumented router tail or cost freeze is established.']}
(p/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2))
selected={(x['backend_request_id']+'-0'):x for x in requests if x['batch']==1 and not x['warmup'] and x['status']==200}
firsts={}
for line in (p/'compute-events-83657.jsonl').open():
 e=json.loads(line)
 if e.get('event')!='model_step': continue
 for g in e.get('groups',[]):
  rid2=g['request_id']
  if rid2 in selected and g['is_prompt']:
   if rid2 in firsts:raise ValueError('duplicate first step')
   h=e['host_intervals']['sampler'];firsts[rid2]=(h[1]-h[0])/1e6
assert set(firsts)==set(selected) and len(firsts)==30
vals=sorted(firsts.values())
stat={'n':len(vals),'min_ms':min(vals),'median_ms':statistics.median(vals),'p95_nearest_rank_ms':vals[28],'max_ms':max(vals),'selected_request_ms':firsts[rid],'source':'pd-accounting-20261126 instrumented consumer steps, not post-KV exclusive interval'}
(p/'first-sampler-distribution.json').write_text(json.dumps(stat,indent=2)+'\n');print(json.dumps(stat,indent=2))
