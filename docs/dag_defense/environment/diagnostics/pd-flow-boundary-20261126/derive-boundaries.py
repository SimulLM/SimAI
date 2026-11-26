import json,pathlib,csv,collections,statistics
p=pathlib.Path(__file__).parent
read=lambda f:[json.loads(x) for x in f.read_text().splitlines()]
routes={x['decode_id']:x for x in read(p/'router-events.jsonl') if x.get('decode_id')}
events=collections.defaultdict(list)
for file in p.glob('compute-events-*.jsonl'):
 for e in read(file):
  if e.get('event')=='model_step':
   for rid in e.get('request_ids_to_seq_ids',{}): events[rid].append(e)
rows=[]
for req in read(p/'coverage/requests.jsonl'):
 r=routes[req['backend_request_id']]; pid=r['prefill_id']+'-0';did=r['decode_id']+'-0'
 pr=next(e for e in events[pid] if 'send_kv_caches_and_hidden_states' in e['host_intervals'])
 d=events[did]; rec=next(e for e in d if 'recv_kv_caches_and_hidden_states' in e['host_intervals']); first=next(e for e in d if any(g['request_id']==did and not g['is_prompt'] for g in e['groups']))
 row={'router_id':r['router_id'],'prefill_id':r['prefill_id'],'decode_id':r['decode_id'],'input_tokens':req['length'],'requested_batch':req['batch'],'wave':req['wave'],'warmup':req['warmup'],'arrival_ns':r['arrival_ns'],'prefill_step_host_start_ns':pr['host_start_ns'],'prefill_send_api_return_ns':pr['host_intervals']['send_kv_caches_and_hidden_states'][1],'prefill_step_after_sync_ns':pr['host_after_sync_ns'],'prefill_response_ns':r['prefill_done_ns'],'decode_submit_ns':r['decode_submit_ns'],'decode_kv_step_host_start_ns':rec['host_start_ns'],'recv_api_start_ns':rec['host_intervals']['recv_kv_caches_and_hidden_states'][0],'recv_api_return_ns':rec['host_intervals']['recv_kv_caches_and_hidden_states'][1],'kv_ready_upper_bound_after_step_sync_ns':rec['host_after_sync_ns'],'first_decode_forward_host_start_ns':first['host_start_ns'],'router_complete_ns':r['router_complete_ns']}
 rows.append(row)
with (p/'derived-boundaries.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
violations=[]
for r in rows:
 keys=['arrival_ns','prefill_step_host_start_ns','prefill_send_api_return_ns','prefill_step_after_sync_ns','prefill_response_ns','decode_submit_ns','decode_kv_step_host_start_ns','recv_api_start_ns','recv_api_return_ns','kv_ready_upper_bound_after_step_sync_ns','first_decode_forward_host_start_ns','router_complete_ns']
 if any(r[a]>r[b] for a,b in zip(keys,keys[1:])): violations.append(r['router_id'])
print(json.dumps({'rows':len(rows),'ordered':len(rows)-len(violations),'violations':violations,'recv_exec_after_decode_submit':sum(r['recv_api_start_ns']>=r['decode_submit_ns'] for r in rows),'kv_ready_upper_bound':'synchronize after entire first consumer step, includes logits and sampling; not exact KVReady'},indent=2))
