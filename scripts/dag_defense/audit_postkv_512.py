"""Audit independent 512-token serial post-KV synchronized intervals."""
import csv,hashlib,json,math,pathlib,statistics,sys
root=pathlib.Path(sys.argv[1]);out=pathlib.Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=False)
assert (root/'exit').read_text().strip()=='0'
req=[json.loads(x) for x in (root/'coverage/requests.jsonl').read_text().splitlines()];routes=[json.loads(x) for x in (root/'router-events.jsonl').read_text().splitlines()]
assert len(req)==len(routes)==40
route={r['decode_id']:r for r in routes};assert len(route)==40
steps={}
for f in root.glob('compute-events-*.jsonl'):
 for line in f.read_text().splitlines():
  e=json.loads(line)
  if e.get('event')=='model_step' and e.get('host_intervals',{}).get('kv_bypass'):
   for rid in e.get('request_ids_to_seq_ids',{}):
    if rid in steps:raise ValueError('duplicate consumer bypass step')
    steps[rid]=e
rows=[]
for r in req:
 assert r['length']==512 and r['batch']==1 and r['status']==200 and r['usage']['prompt_tokens']==512 and r['usage']['completion_tokens']==8
 rt=route[r['backend_request_id']];e=steps[rt['decode_id']+'-0'];h=e['host_intervals'];s=h['kv_ready_sync_ns'][1];end=e['host_after_sync_ns']
 assert e['query_lens']==[512] and s<=h['logits'][0]<=h['logits'][1]<=h['sampler'][0]<=h['sampler'][1]<=end
 rows.append({'wave':r['wave'],'warmup':r['warmup'],'decode_id':rt['decode_id'],'sync_end_ns':s,'step_end_ns':end,'host_post_sync_ms':(end-s)/1e6,'logits_gpu_ms':e['gpu_event_ms']['logits_gpu'],'sampler_gpu_ms':e['gpu_event_ms']['sampler_gpu']})
assert len({r['decode_id'] for r in rows})==40 and sum(r['warmup'] for r in rows)==10
meas=[r for r in rows if not r['warmup']];assert len(meas)==30
def stats(key):
 xs=sorted(r[key] for r in meas);return {'median_ms':statistics.median(xs),'min_ms':xs[0],'max_ms':xs[-1],'p95_nearest_rank_ms':xs[math.ceil(.95*len(xs))-1]}
with (out/'samples.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
result={'status':'instrumented_independent_diagnostic_not_frozen','warmup':10,'measured':30,'input_tokens':512,'output_tokens':8,'concurrency':1,'statistics':{k:stats(k) for k in ('host_post_sync_ms','logits_gpu_ms','sampler_gpu_ms')},'limitations':['CUDA and host intervals overlap and are not additive','Device-wide synchronization changes the scheduling and may add overhead','Does not cover concurrent batch shapes or provide noninstrumented CPU overhead','Measured post-KV interval is not a validated common simulator fee or formal E2E']}
(out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
