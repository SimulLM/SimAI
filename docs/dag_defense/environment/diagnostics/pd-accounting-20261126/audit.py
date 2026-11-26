import json, pathlib, collections, statistics
p=pathlib.Path(__file__).parent
rows=[json.loads(x) for x in (p/'coverage-retry/requests.jsonl').read_text().splitlines()]
events=[json.loads(x) for x in (p/'compute-events-83657.jsonl').read_text().splitlines()]
byid=collections.defaultdict(list)
for e in events:
 if e.get('event')=='model_step':
  for rid in e.get('request_ids_to_seq_ids',{}): byid[rid].append(e)
counts=collections.Counter(); samples=collections.defaultdict(list); missing=[]
for r in rows:
 rid=(r.get('backend_request_id') or '')+'-0'; ev=byid.get(rid,[])
 prompt=[e for e in ev if any(g.get('request_id')==rid and g.get('is_prompt') for g in e['groups'])]
 decode=[e for e in ev if any(g.get('request_id')==rid and not g.get('is_prompt') for g in e['groups'])]
 ok=len(prompt)==1 and len(decode)==63 and all('logits_gpu' in e['gpu_event_ms'] and 'sampler_gpu' in e['gpu_event_ms'] for e in ev) and 'full_model_forward' not in prompt[0]['gpu_event_ms'] if prompt else False
 counts[(r['batch'],r['warmup'],len(prompt),len(decode),ok)]+=1
 if not ok: missing.append(rid)
 if not r['warmup'] and ok:
  e=prompt[0]; actual=len(e['request_ids_to_seq_ids'])
  for key in ('logits_gpu','sampler_gpu','step_gpu_ms'):
   v=e['gpu_event_ms'].get(key) if key!='step_gpu_ms' else e[key]
   samples[(r['batch'],actual,key)].append(v)
result={'requests':len(rows),'status_counts':dict(collections.Counter(str(r['status']) for r in rows)),'event_match_counts':[{'requested_batch':k[0],'warmup':k[1],'first_steps':k[2],'decode_steps':k[3],'valid':k[4],'n':v} for k,v in sorted(counts.items())], 'first_step_gpu_medians_ms':[{'requested_batch':k[0],'actual_batch':k[1],'metric':k[2],'n_request_observations':len(v),'median_ms':statistics.median(v)} for k,v in sorted(samples.items())], 'unmatched_or_invalid':missing, 'limitations':'Per-request observations share batch events; GPU event timings include asynchronous gaps; first-step total includes receive wait; no additive CPU/GPU or frozen cost claim.'}
(p/'audit.json').write_text(json.dumps(result,indent=2)+'\n'); print(json.dumps(result,indent=2))
