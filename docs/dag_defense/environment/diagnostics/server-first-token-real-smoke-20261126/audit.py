import collections,hashlib,json,pathlib
p=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/server-first-token-smoke-20261126');out=pathlib.Path(__file__).parent
assert (p/'exit').read_text().strip()=='0'; clients=json.loads((p/'client.json').read_text());assert len(clients)==2
es=collections.defaultdict(dict)
for line in (p/'service/router-events.jsonl').read_text().splitlines():
 e=json.loads(line); assert e['event'] not in es[e['request_id']];es[e['request_id']][e['event']]=e
results=[]
for c in clients:
 e=es[c['router_id']];assert c['http_status']==200 and c['done'] and c['usage']['prompt_tokens']==512 and c['usage']['completion_tokens']==64
 names=('server_arrival','prefill_send','prefill_response','prefill_mapping','decode_send','decode_mapping','server_first_token','server_final_choice_observed','server_complete'); ts=[e[n]['timestamp_ns'] for n in names];assert ts==sorted(ts) and all(e[n]['clock_id']=='CLOCK_MONOTONIC' for n in names)
 first=next(x for x in c['chunks'] if (x.get('usage') or {}).get('completion_tokens',0)>0);assert first['usage']['completion_tokens']==1 and e['server_first_token']['completion_tokens']==1 and e['server_first_token']['timestamp_ns']<=first['ns'];assert e['decode_mapping']['backend_request_id']==c['backend_id'];assert e['server_final_choice_observed']['finish_reasons']==['length'] and e['server_complete']['usage']==c['usage']
 results.append({'stage':c['stage'],'router_id':c['router_id'],'backend_id':c['backend_id'],'timestamps_ns':{n:e[n]['timestamp_ns'] for n in names},'client_first_token_ns':first['ns'],'client_complete_ns':c['client_complete_ns'],'server_e2e_s':(ts[-1]-ts[0])/1e9,'first_router_to_client_ms':(first['ns']-ts[-3])/1e6,'final_choice_to_complete_ms':(ts[-1]-ts[-2])/1e6})
result={'status':'passed','results':results,'input_tokens':512,'output_tokens':64,'limitations':['one warmup and one measured request','not formal collector or validation','host timestamps do not establish exact GPU KVReady','does not close simulator completion boundary']};(out/'audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
