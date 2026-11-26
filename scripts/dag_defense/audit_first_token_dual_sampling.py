"""Audit mapped producer/consumer first-step operations from real diagnostic."""
import collections,csv,hashlib,json,pathlib,statistics,sys
p=pathlib.Path(sys.argv[1]);out=pathlib.Path(sys.argv[2]);out.mkdir(exist_ok=False)
if (p/'exit').read_text().strip()!='0':raise ValueError('source run failed')
def read(f):return [json.loads(x) for x in f.read_text().splitlines()]
requests=read(p/'client/requests.jsonl');routes={r['decode_id']:r for r in read(p/'router-events.jsonl') if r.get('decode_id')};events=collections.defaultdict(list)
for f in p.glob('compute-events-*.jsonl'):
 for e in read(f):
  if e.get('event')=='model_step':
   for rid in e.get('request_ids_to_seq_ids',{}):events[rid].append(e)
rows=[]
for r in requests:
 if r['status']!=200 or r['usage']['prompt_tokens']!=512 or r['usage']['completion_tokens']!=8:raise ValueError('request failed')
 route=routes[r['backend_request_id']];pref=events[route['prefill_id']+'-0'];dec=events[route['decode_id']+'-0'];first=[e for e in dec if any(g['request_id']==route['decode_id']+'-0' and g['is_prompt'] for g in e['groups'])];later=[e for e in dec if any(g['request_id']==route['decode_id']+'-0' and not g['is_prompt'] for g in e['groups'])]
 if len(pref)!=1 or len(first)!=1 or len(later)!=7:raise ValueError('unexpected step count')
 a,b=pref[0],first[0]
 if not b['host_intervals'].get('kv_bypass') or any(k not in e['gpu_event_ms'] for e in (a,b) for k in ('logits_gpu','sampler_gpu')):raise ValueError('missing operation or KV bypass')
 if any(k not in e['host_intervals'] for e in (a,b) for k in ('logits','sampler')):raise ValueError('missing host interval')
 if not a['host_after_sync_ns']<=route['prefill_done_ns']<=route['decode_submit_ns']<=b['host_start_ns']:raise ValueError('host order mismatch')
 row={'wave':r['wave'],'warmup':r['warmup'],'router_id':route['router_id'],'prefill_id':route['prefill_id'],'decode_id':route['decode_id'],'producer_logits_gpu_ms':a['gpu_event_ms']['logits_gpu'],'producer_sampler_gpu_ms':a['gpu_event_ms']['sampler_gpu'],'consumer_logits_gpu_ms':b['gpu_event_ms']['logits_gpu'],'consumer_sampler_gpu_ms':b['gpu_event_ms']['sampler_gpu'],'producer_sampler_host_ms':(a['host_intervals']['sampler'][1]-a['host_intervals']['sampler'][0])/1e6,'consumer_sampler_host_ms':(b['host_intervals']['sampler'][1]-b['host_intervals']['sampler'][0])/1e6,'consumer_later_decode_steps':len(later)};rows.append(row)
if len(rows)!=40 or sum(not x['warmup'] for x in rows)!=30:raise ValueError('coverage mismatch')
with (out/'requests.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
measured=[r for r in rows if not r['warmup']];metrics=[k for k in rows[0] if k.endswith('_ms')];summary={'status':'diagnostic_only','requests':len(rows),'measured':len(measured),'median_ms':{k:statistics.median(r[k] for r in measured) for k in metrics},'source_hashes':{str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in [p/'client/requests.jsonl',p/'router-events.jsonl',*sorted(p.glob('compute-events-*.jsonl'))]},'limitations':['Instrumented synchronized 512-input/8-output serial diagnostic only','GPU CUDA event and CPU host intervals can overlap and cannot be added as independent fees','Consumer first-step interval includes KV receive; no exact GPU KVReady','Simulator Prefill accounting and consumer first token are not yet reconciled','No formal validation or calibrated fee claim']};(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
