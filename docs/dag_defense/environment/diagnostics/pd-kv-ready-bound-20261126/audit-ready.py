import json,pathlib,collections,statistics,csv
p=pathlib.Path(__file__).parent
read=lambda f:[json.loads(x) for x in f.read_text().splitlines()]
requests=read(p/'coverage/requests.jsonl');routes={x['decode_id']:x for x in read(p/'router-events.jsonl') if x.get('decode_id')};byid=collections.defaultdict(list)
for f in p.glob('compute-events-*.jsonl'):
 for e in read(f):
  if e.get('event')=='model_step':
   for rid in e.get('request_ids_to_seq_ids',{}):byid[rid].append(e)
rows=[];issues=[];distinct=collections.defaultdict(dict)
for req in requests:
 r=routes.get(req.get('backend_request_id'))
 if not r:issues.append({'decode_id':req.get('backend_request_id'),'reason':'missing router'});continue
 did=r['decode_id']+'-0'; ev=byid[did]; rec=[e for e in ev if 'kv_ready_bound_ns' in e.get('host_intervals',{})]; dec=[e for e in ev if any(x.get('request_id')==did and not x.get('is_prompt') for x in e.get('groups',[]))]
 if len(rec)!=1 or len(dec)!=7:issues.append({'decode_id':did,'reason':'step count'});continue
 e=rec[0]; h=e['host_intervals']; lo,hi=h['kv_ready_bound_ns']; ss,se=h['kv_ready_sync_ns'];recv=h['recv_kv_caches_and_hidden_states'];step=dec[0]
 ok=(lo is not None and h['kv_bypass'] is True and r['decode_submit_ns']<=e['host_start_ns']<=recv[0]<=lo<=recv[1]<=ss<=se==hi<=e['host_after_sync_ns']<=step['host_start_ns']<=r['router_complete_ns'])
 if not ok:issues.append({'decode_id':did,'reason':'ordering','intervals':h})
 row={'router_id':r['router_id'],'prefill_id':r['prefill_id'],'decode_id':r['decode_id'],'input_tokens':req['length'],'requested_batch':req['batch'],'wave':req['wave'],'warmup':req['warmup'],'consumer_batch':len(e['request_ids_to_seq_ids']),'decode_submit_ns':r['decode_submit_ns'],'recv_start_ns':recv[0],'last_kv_install_api_start_ns':lo,'recv_return_ns':recv[1],'device_sync_start_ns':ss,'kv_ready_upper_bound_ns':hi,'consumer_step_after_sync_ns':e['host_after_sync_ns'],'first_decode_step_host_start_ns':step['host_start_ns'],'router_complete_ns':r['router_complete_ns'],'bound_width_ms':(hi-lo)/1e6,'sync_wait_ms':(se-ss)/1e6,'valid':ok};rows.append(row)
 if not req['warmup']:
  key=(req['length'],req['batch'],len(e['request_ids_to_seq_ids']));distinct[key][(e['pid'],e['host_start_ns'])]=row
with (p/'kv-ready-bounds.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
summ=[]
for key,values in sorted(distinct.items()):
 rr=list(values.values());summ.append({'input_tokens':key[0],'requested_batch':key[1],'actual_batch':key[2],'distinct_steps':len(rr),'median_bound_width_ms':statistics.median(x['bound_width_ms'] for x in rr),'max_bound_width_ms':max(x['bound_width_ms'] for x in rr),'median_sync_wait_ms':statistics.median(x['sync_wait_ms'] for x in rr)})
out={'request_count':len(requests),'status_counts':dict(collections.Counter(str(x['status']) for x in requests)),'mapped':len(rows),'issues':issues,'summary':summ,'meaning':'Bounds apply to completion of all KV cache installations in the consumer batch: lower is CPU entry into its last install call, upper follows device-wide sync after all calls. For an individual request the lower bound is recv_start_ns, because earlier requests may be ready sooner. Not an exact GPU timestamp; synchronization changes execution.'}
(p/'kv-ready-audit.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
