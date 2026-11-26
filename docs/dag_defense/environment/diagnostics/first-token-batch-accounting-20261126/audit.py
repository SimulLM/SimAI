import collections,csv,hashlib,json,pathlib,statistics,tarfile
p=pathlib.Path('/root/autodl-tmp/SimAI-handoff/docs/dag_defense/environment/diagnostics/pd-kv-ready-bound-20261126/raw.tar.gz');out=pathlib.Path(__file__).parent
with tarfile.open(p) as t:
 def read(name):return [json.loads(x) for x in t.extractfile(name)]
 req=read('coverage/requests.jsonl');route={x['decode_id']:x for x in read('router-events.jsonl') if x.get('decode_id')};events=collections.defaultdict(list)
 for name in ('compute-events-86396.jsonl','compute-events-86401.jsonl'):
  for e in read(name):
   if e.get('event')=='model_step':
    for rid in e.get('request_ids_to_seq_ids',{}):events[rid].append(e)
 steps={};seen=set()
 for r in req:
  assert r['status']==200 and r['usage']['prompt_tokens']==r['length'] and r['usage']['completion_tokens']==8
  assert r['backend_request_id'] in route;rid=route[r['backend_request_id']]['decode_id']+'-0';assert rid not in seen;seen.add(rid)
  matched=[e for e in events[rid] if 'kv_ready_sync_ns' in e.get('host_intervals',{})];assert len(matched)==1;e=matched[0];h=e['host_intervals'];sync=h['kv_ready_sync_ns'][1];end=e['host_after_sync_ns'];assert h['kv_bypass'] and sync<=end
  key=(e['pid'],e['host_start_ns']);entry=steps.setdefault(key,{'input_tokens':r['length'],'requested_concurrency':r['batch'],'wave':r['wave'],'warmup':r['warmup'],'pid':e['pid'],'step_start_ns':key[1],'step_ids':sorted(e['request_ids_to_seq_ids']),'mapped_ids':[],'post_sync_host_ms':(end-sync)/1e6,'logits_gpu_ms':e['gpu_event_ms']['logits_gpu'],'sampler_gpu_ms':e['gpu_event_ms']['sampler_gpu']})
  assert (entry['input_tokens'],entry['requested_concurrency'],entry['wave'],entry['warmup'])==(r['length'],r['batch'],r['wave'],r['warmup']);entry['mapped_ids'].append(rid)
rows=[];group=collections.defaultdict(list)
for x in steps.values():
 x['mapped_ids'].sort();assert x['mapped_ids']==x['step_ids'];x['actual_batch']=len(x['mapped_ids']);x['request_weighted_interval_ms']=x['post_sync_host_ms']*x['actual_batch'];x['potential_duplicate_ms']=x['request_weighted_interval_ms']-x['post_sync_host_ms'];group[(x['input_tokens'],x['requested_concurrency'],x['actual_batch'],x['warmup'])].append(x);rows.append(x)
summary=[]
for (n,b,actual,warm),values in sorted(group.items()):
 summary.append({'input_tokens':n,'requested_concurrency':b,'actual_batch':actual,'warmup':warm,'steps':len(values),'distinct_waves':len({x['wave'] for x in values}),'requests':sum(x['actual_batch'] for x in values),'host_median_ms':statistics.median(x['post_sync_host_ms'] for x in values),'step_host_sum_ms':sum(x['post_sync_host_ms'] for x in values),'request_weighted_host_sum_ms':sum(x['request_weighted_interval_ms'] for x in values),'potential_duplicate_ms':sum(x['potential_duplicate_ms'] for x in values)})
with (out/'distinct-steps.jsonl').open('w') as f:
 for x in rows:f.write(json.dumps(x,sort_keys=True)+'\n')
with (out/'summary.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=summary[0]);w.writeheader();w.writerows(summary)
result={'source_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'requests':len(req),'unique_request_ids':len(seen),'distinct_steps':len(steps),'all_step_ids_reconciled':True,'shared_steps':sum(1 for x in rows if x['actual_batch']>1),'measured_shared_steps':sum(1 for x in rows if x['actual_batch']>1 and not x['warmup']),'diagnostic':'request-weighted sum illustrates duplication if the same shared inclusive host step were charged to each request as independent work; not a production fee or wall-clock savings','limitations':['per-tensor synchronization changes scheduling','same request wave may contain multiple distinct steps','host interval includes logits, sampler and synchronization, so CUDA subintervals cannot be added','shared host interval does not define resource occupancy','8-output diagnostics; no production validation']};(out/'audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
