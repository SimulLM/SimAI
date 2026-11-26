"""Extract serial dispatch boundary from independent instrumented 512-token run."""
import collections,csv,hashlib,json,pathlib,statistics,sys
p=pathlib.Path(sys.argv[1]);out=pathlib.Path(sys.argv[2]);out.mkdir(exist_ok=False)
if (p/'exit').read_text().strip()!='0':raise ValueError('run did not succeed')
read=lambda f:[json.loads(x) for x in f.read_text().splitlines()]
req=read(p/'client/requests.jsonl');routes=read(p/'router-events.jsonl');route={x['decode_id']:x for x in routes if x.get('decode_id')};events=collections.defaultdict(list)
for f in p.glob('compute-events-*.jsonl'):
 for e in read(f):
  if e.get('event')=='model_step':
   for rid in e.get('request_ids_to_seq_ids',{}):events[rid].append(e)
rows=[]
for r in req:
 if r.get('status')!=200 or r.get('usage',{}).get('prompt_tokens')!=512 or r.get('usage',{}).get('completion_tokens')!=8:raise ValueError('bad request')
 x=route[r['backend_request_id']];pref=[e for e in events[x['prefill_id']+'-0'] if 'send_kv_caches_and_hidden_states' in e.get('host_intervals',{})];cons=[e for e in events[x['decode_id']+'-0'] if 'recv_kv_caches_and_hidden_states' in e.get('host_intervals',{})]
 if len(pref)!=1 or len(cons)!=1:raise ValueError('missing or duplicate producer/consumer steps')
 a=pref[0]['host_after_sync_ns'];b=x['prefill_done_ns'];c=x['decode_submit_ns'];d=cons[0]['host_start_ns'];e=cons[0]['host_intervals']['recv_kv_caches_and_hidden_states'][0]
 if not(a<=b<=c<=d<=e):raise ValueError('host timing order')
 rows.append({'wave':r['wave'],'warmup':r['warmup'],'router_id':x['router_id'],'prefill_id':x['prefill_id'],'decode_id':x['decode_id'],'prefill_after_sync_ns':a,'router_prefill_response_ns':b,'decode_submit_ns':c,'consumer_step_start_ns':d,'receive_start_ns':e,'after_sync_to_consumer_step_s':(d-a)/1e9})
if len(rows)!=40 or sum(not r['warmup'] for r in rows)!=30 or len({r['router_id'] for r in rows})!=40:raise ValueError('coverage mismatch')
with (out/'requests.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
values=sorted(x['after_sync_to_consumer_step_s'] for x in rows if not x['warmup']);files=[p/'client/requests.jsonl',p/'router-events.jsonl',*sorted(p.glob('compute-events-*.jsonl'))]
summary={'status':'independent_instrumented_diagnostic','warmup':10,'measured':len(values),'median_s':statistics.median(values),'min_s':min(values),'max_s':max(values),'p95_nearest_rank_s':values[28],'source_hashes':{str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in files},'limitations':['Single request at a time; 8 output tokens','Host interval includes router processing, consumer scheduling and instrumentation','Producer after-sync is an upper host boundary, not exact GPU Prefill completion','Not a standalone CPU cost or proven general concurrent dispatch delay','No validation or cost freeze']};(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
