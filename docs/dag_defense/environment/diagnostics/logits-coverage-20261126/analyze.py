import collections,csv,json,pathlib,statistics,math,hashlib
p=pathlib.Path(__file__).parent
read=lambda path:[json.loads(l) for l in path.open()]
requests=read(p/'coverage/requests.jsonl');routes={r['decode_id']:r for r in read(p/'router-events.jsonl') if r.get('decode_id')}
lookup={}
for r in requests:
 assert r['status']==200 and r['usage']['prompt_tokens']==r['length'] and r['usage']['completion_tokens']==8
 route=routes[r['backend_request_id']];rid=route['decode_id']+'-0';assert rid not in lookup;lookup[rid]=r
assert len(lookup)==560
waves=collections.defaultdict(list);seen=set();per_request=collections.Counter()
for f in sorted(p.glob('compute-events-*.jsonl')):
 for e in read(f):
  if e.get('event')!='model_step':continue
  groups=e.get('groups',[]);members=[g['request_id'] for g in groups if g['request_id'] in lookup and not g['is_prompt']]
  if not members:continue
  assert len(members)==len(groups)==len(e['request_ids_to_seq_ids'])
  source=[lookup[i] for i in members];shape={(r['length'],r['batch'],r['wave'],r['warmup']) for r in source};assert len(shape)==1,shape
  key=next(iter(shape));identity=(e['pid'],e['host_start_ns']);assert identity not in seen;seen.add(identity)
  for rid in members:per_request[rid]+=1
  t=e['gpu_event_ms'];assert 'logits_gpu' in t and 'sampler_gpu' in t
  waves[(*key,len(members))].append(t['logits_gpu'])
assert len(per_request)==560 and set(per_request.values())=={7}
rows=[]
for (length,requested,wave,warmup,actual),vals in sorted(waves.items()):rows.append({'input_tokens':length,'requested_concurrency':requested,'wave':wave,'warmup':warmup,'actual_batch':actual,'distinct_steps':len(vals),'wave_median_logits_ms':statistics.median(vals)})
with (p/'wave-medians.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
groups=collections.defaultdict(list)
for x in rows:groups[(x['input_tokens'],x['actual_batch'],x['warmup'])].append(x['wave_median_logits_ms'])
summary=[]
for length in (1024,2048):
 for actual in (1,2,3,4):
  vals=groups[(length,actual,False)];warm=groups[(length,actual,True)];summary.append({'input_tokens':length,'actual_batch':actual,'warmup_waves':len(warm),'measured_waves':len(vals),'median_wave_median_ms':statistics.median(vals) if vals else None,'eligible_10_30':len(warm)>=10 and len(vals)>=30})
result={'status':'observed_instrumented_decode_logits_coverage','rows':summary,'requests':len(lookup),'deduplicated_steps':len(seen),'limitations':['8-output diagnostic only, not 128-output context coverage','GPU event intervals may contain idle gaps; sync and hooks perturb timing','multiple waves share one session; not independent restart repetitions','batch composition and requested concurrency differ','not a frozen or additive cost']}
(p/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
