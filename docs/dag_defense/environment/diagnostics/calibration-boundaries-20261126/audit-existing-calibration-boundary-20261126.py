import json,pathlib,collections,statistics,csv,hashlib
root=pathlib.Path('/root/autodl-tmp/dag-handoff/runs');out=root/'calibration-boundary-audit-20261126';out.mkdir(exist_ok=False)
reqpath=root/'calibration-merged-20261126/requests.json';eventpath=root/'calibration-server-20261126/router-events.jsonl';req=json.loads(reqpath.read_text()); events=collections.defaultdict(lambda:collections.defaultdict(list))
for line in eventpath.read_text().splitlines():
 e=json.loads(line);events[e['request_id']][e['event']].append(e)
rows=[];missing=[];errors=[]
for r in req:
 rid=r['router_id'];ev=events[rid]; names=['server_arrival','prefill_send','prefill_response','prefill_mapping','decode_send','decode_mapping','server_first_token','server_complete']
 absent=[x for x in names if len(ev[x])!=1]
 if absent:missing.append({'id':rid,'events':absent});continue
 time=lambda x:ev[x][0]['timestamp_ns']; t={x:time(x) for x in names};ok=t['server_arrival']<=t['prefill_send']<=t['prefill_response']<=t['prefill_mapping']<=t['decode_send']<=t['decode_mapping']<=t['server_complete'] and t['decode_mapping']<=t['server_first_token']<=t['server_complete']
 if not ok:errors.append({'id':rid,'timestamps':t})
 if ev['decode_mapping'][0].get('backend_request_id')!=r.get('decode_id'):errors.append({'id':rid,'error':'decode id mismatch'})
 row={'router_id':rid,'repeat':r['repeat'],'mode':r['mode'],'status':r['status'],'ordered':ok,'server_e2e_ms':(t['server_complete']-t['server_arrival'])/1e6,'prefill_response_ms':(t['prefill_response']-t['prefill_send'])/1e6,'router_to_decode_submit_ms':(t['decode_send']-t['prefill_response'])/1e6,'decode_to_first_token_ms':(t['server_first_token']-t['decode_send'])/1e6,'first_token_to_complete_ms':(t['server_complete']-t['server_first_token'])/1e6,'client_e2e_ms':(r['complete_ns']-r['send_ns'])/1e6};rows.append(row)
with (out/'request-boundaries.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
summary=[]
for mode in ('serial','concurrent2'):
 a=[x for x in rows if x['mode']==mode];summary.append({'mode':mode,'requests':len(a),**{k+'_median':statistics.median(x[k] for x in a) for k in ('server_e2e_ms','prefill_response_ms','router_to_decode_submit_ms','decode_to_first_token_ms','first_token_to_complete_ms','client_e2e_ms')}})
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();res={'status':'observed_existing_calibration_boundary_only','requests':len(req),'mapped':len(rows),'missing':missing,'errors':errors,'summary':summary,'source_sha256':{'requests':sha(reqpath),'router_events':sha(eventpath)},'limitations':['This is existing calibration, not validation; no fee is fitted to these end-to-end times','Router events are host service boundaries, not GPU KVReady or GPU execution completion','Calibration mode is eager with 8GiB KV buffer and gpu utilization 0.75; traces may include profiler-independent router processing','All three serial repeats include separately collected supplement requests; verify per-repeat idle and input provenance before treating as final calibration','Decode response mapping and first token are stream processing timestamps; no attribution to individual GPU or CPU components']};(out/'audit.json').write_text(json.dumps(res,indent=2)+'\n');print(json.dumps(res,indent=2))
