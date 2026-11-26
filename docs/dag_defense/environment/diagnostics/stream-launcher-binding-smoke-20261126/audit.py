import collections,json,pathlib
p=pathlib.Path(__file__).parent;clients=json.loads((p/'client.json').read_text());assert len(clients)==2
byid=collections.defaultdict(list)
for line in (p/'service/router-events.jsonl').open():
 x=json.loads(line);byid[x['request_id']].append(x)
result=[]
for row in clients:
 assert row['http_status']==200 and row['done'] and row['usage']['prompt_tokens']==512 and row['usage']['completion_tokens']==64
 events=byid[row['router_id']]; e={x['event']:x for x in events}; assert len(e)==len(events)
 names=['server_arrival','prefill_send','prefill_response','prefill_mapping','decode_send','decode_mapping','server_first_token','server_final_choice_observed','server_complete']; assert all(name in e for name in names)
 assert [e[x]['timestamp_ns'] for x in names]==sorted(e[x]['timestamp_ns'] for x in names)
 assert e['server_arrival']['client_request_id']=='single-stream-'+row['stage'];assert e['decode_mapping']['backend_request_id']==row['backend_id'];assert e['server_final_choice_observed']['finish_reasons']==['length'];assert e['server_complete']['usage']['completion_tokens']==64
 result.append({'stage':row['stage'],'router_id':row['router_id'],'backend_id':row['backend_id'],'ordered_events':names})
(p/'audit.json').write_text(json.dumps({'status':'passed','requests':result,'limitations':['launcher binding smoke only; no GPU KV events, idle gate, freeze or formal validation']},indent=2)+'\n');print('PASS two real requests and versioned router ID/final-choice events')
