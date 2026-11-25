import json,os
from pathlib import Path
r=Path(os.environ['PD_ROUTE_DIR']); rows=json.loads((r/'concurrent-results.json').read_text());events=[json.loads(x) for x in (r/'router-events.jsonl').read_text().splitlines()];assert len(rows)==4
prefill_ids=[];decode_ids=[]
for row in rows:
 assert row['status']==200 and row['done'] and row['usage']['prompt_tokens']==512 and row['usage']['completion_tokens']==8 and row['send_ns']<=row['first_token_ns']<=row['complete_ns']
 assert row['token_counts']==list(range(1,9))+[8]
 es=[x for x in events if x['request_id']==row['router_id']]
 assert [x['event'] for x in es]==['server_arrival','prefill_send','prefill_response','prefill_mapping','decode_send','decode_mapping','server_first_token','server_complete']
 assert [x['timestamp_ns'] for x in es]==sorted(x['timestamp_ns'] for x in es)
 assert row['send_ns']<=es[0]['timestamp_ns'] and es[6]['timestamp_ns']<=row['first_token_ns'] and es[-1]['usage']==row['usage']
 assert row['decode_id']==es[5]['backend_request_id'];prefill_ids.append(es[3]['backend_request_id']);decode_ids.append(es[5]['backend_request_id'])
assert len(set(prefill_ids))==len(set(decode_ids))==4
report={'status':'passed','concurrency':4,'input_tokens':512,'output_tokens':8,'distinct_prefill_ids':len(set(prefill_ids)),'distinct_decode_ids':len(set(decode_ids)),'note':'API ID association and token counts verified; connector per-tensor association requires separate instrumentation'}
(r/'concurrent-verification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
