"""Summarize real consumer first-step host interval after instrumented KV sync."""
import collections,csv,hashlib,json,pathlib,statistics,sys,tarfile
archive=pathlib.Path(sys.argv[1]);out=pathlib.Path(sys.argv[2]);out.mkdir(exist_ok=False)
with tarfile.open(archive) as t:
 def read(name):return [json.loads(x) for x in t.extractfile(name)]
 req=read('coverage/requests.jsonl');route={x['decode_id']:x for x in read('router-events.jsonl') if x.get('decode_id')}; events=collections.defaultdict(list)
 for name in ('compute-events-86396.jsonl','compute-events-86401.jsonl'):
  for e in read(name):
   if e.get('event')=='model_step':
    for rid in e.get('request_ids_to_seq_ids',{}):events[rid].append(e)
 groups=collections.defaultdict(dict);issues=[]
 for r in req:
  if r.get('status')!=200 or r.get('usage',{}).get('prompt_tokens')!=r['length'] or r.get('usage',{}).get('completion_tokens')!=8:raise ValueError('request failure')
  x=route.get(r['backend_request_id']);rid=(x['decode_id']+'-0') if x else None
  matched=[e for e in events[rid] if 'kv_ready_sync_ns' in e.get('host_intervals',{})]
  if len(matched)!=1:raise ValueError('missing first-step event')
  e=matched[0];h=e['host_intervals'];sync=h['kv_ready_sync_ns'][1];end=e['host_after_sync_ns'];logits=h.get('logits');sampler=h.get('sampler')
  if not (h.get('kv_bypass') and logits and sampler and sync<=logits[0]<=logits[1]<=sampler[0]<=sampler[1]<=end):raise ValueError('first-step boundary ordering mismatch')
  key=(r['length'],r['batch'],len(e['request_ids_to_seq_ids']));wave=(r['wave'],r['warmup']);step=(e['pid'],e['host_start_ns'])
  row={'input_tokens':r['length'],'requested_concurrency':r['batch'],'actual_batch':key[2],'wave':r['wave'],'warmup':r['warmup'],'pid':e['pid'],'step_start_ns':e['host_start_ns'],'kv_sync_complete_ns':sync,'first_step_sync_complete_ns':end,'post_sync_host_ms':(end-sync)/1e6,'logits_gpu_ms':e['gpu_event_ms']['logits_gpu'],'sampler_gpu_ms':e['gpu_event_ms']['sampler_gpu']}
  groups[key][step]=row
rows=[r for g in groups.values() for r in g.values()]
with (out/'distinct-steps.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
summ=[]
for key,steps in sorted(groups.items()):
 rows1=[r for r in steps.values() if not r['warmup']];warm=[r for r in steps.values() if r['warmup']];waves=len({r['wave'] for r in rows1});warmwaves=len({r['wave'] for r in warm});metrics=('post_sync_host_ms','logits_gpu_ms','sampler_gpu_ms')
 summ.append({'input_tokens':key[0],'requested_concurrency':key[1],'actual_batch':key[2],'measured_steps':len(rows1),'measured_distinct_waves':waves,'warmup_distinct_waves':warmwaves,'medians_ms':{k:statistics.median(r[k] for r in rows1) if rows1 else None for k in metrics},'sample_threshold_met':waves>=30 and warmwaves>=10})
result={'status':'instrumented_diagnostic_only','archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'requests':len(req),'distinct_steps':len(rows),'groups':summ,'limitations':['Explicit device synchronize after KV receive alters execution','Host post-sync interval includes logits, sampling, Python and final synchronization','CUDA and host intervals overlap and must not be summed','No separate non-instrumented CPU cost or 512-token measurement','Batch-shape coverage is determined by actual groups; no formal acceptance','Not validation or final common fee']};(out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
