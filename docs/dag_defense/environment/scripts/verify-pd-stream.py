import json,os
from pathlib import Path
r=Path(os.environ['PD_ROUTE_DIR']);client=json.loads((r/'client-events.json').read_text()); failure=json.loads((r/'failure-response.json').read_text());events=[json.loads(x) for x in (r/'router-events.jsonl').read_text().splitlines()];rid=client[1]['router_id']; success=[e for e in events if e['request_id']==rid];fail=[e for e in events if e['request_id']==failure['router_id']]
assert [x['event'] for x in success]==['server_arrival','prefill_send','prefill_response','prefill_mapping','decode_send','decode_mapping','server_first_token','server_complete']
assert [x['timestamp_ns'] for x in success]==sorted(x['timestamp_ns'] for x in success)
assert [x['event'] for x in fail]==['server_arrival','prefill_send','prefill_response','server_error'] and failure['status']>=400
assert client[0]['timestamp_ns']<=success[0]['timestamp_ns'] and success[6]['timestamp_ns']<=client[2]['timestamp_ns']<=client[3]['timestamp_ns']
assert success[-1]['usage']['prompt_tokens']==512 and success[-1]['usage']['completion_tokens']==8 and client[-1]['usage']==success[-1]['usage']
assert success[5]['backend_request_id']==client[-1]['decode_id'] and success[3]['backend_request_id']!=success[5]['backend_request_id']
counts=[];done=False
for line in (r/'client-response.sse').read_bytes().splitlines():
 if line.startswith(b'data: '):
  payload=line[6:]
  if payload==b'[DONE]':done=True;continue
  row=json.loads(payload)
  if row.get('usage') is not None:counts.append(row['usage']['completion_tokens'])
assert done and counts and counts==sorted(counts) and counts[0]>=1 and counts[-1]==8
out={'status':'passed','request_id':rid,'prefill_id':success[3]['backend_request_id'],'decode_id':success[5]['backend_request_id'],'prompt_tokens':512,'completion_tokens':8,'continuous_token_counts':counts,'server_e2e_ms':(success[-1]['timestamp_ns']-success[0]['timestamp_ns'])/1e6,'client_e2e_ms':(client[-1]['timestamp_ns']-client[0]['timestamp_ns'])/1e6,'client_ttft_ms':(client[2]['timestamp_ns']-client[0]['timestamp_ns'])/1e6,'failure_status':failure['status'],'failure_forwarded_to_decode':False}
(r/'verification.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
