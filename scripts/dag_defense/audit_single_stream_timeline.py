"""Join one real streaming request with lightweight host worker events."""
import collections,json,pathlib,sys
root=pathlib.Path(sys.argv[1]);out=pathlib.Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=False)
assert (root/'exit').read_text().strip()=='0'
clients=json.loads((root/'client.json').read_text());assert len(clients)==2 and clients[-1]['stage']=='measured';c=clients[-1]
assert c['done'] and c['http_status']==200 and c['usage']['prompt_tokens']==512 and c['usage']['completion_tokens']==64
routes=[json.loads(x) for x in (root/'service/router-events.jsonl').read_text().splitlines() if json.loads(x)['request_id']==c['router_id']];r=collections.defaultdict(list)
for event in routes:r[event['event']].append(event)
for key in ('server_arrival','prefill_send','prefill_response','prefill_mapping','decode_send','decode_mapping','server_first_token','server_complete'):assert len(r[key])==1,key
assert r['decode_mapping'][0]['backend_request_id']==c['backend_id']
producer=r['prefill_mapping'][0]['backend_request_id']+'-0';consumer=c['backend_id']+'-0';events=[]
for path in (root/'service/events').glob('*.jsonl'):
 for line in path.read_text().splitlines():
  x=json.loads(line)
  if any(g['request_id'] in (producer,consumer) for g in x.get('groups',[])):events.append(x)
def select(role,name,rid):return sorted([x for x in events if x['role']==role and x['event']==name and any(g['request_id']==rid for g in x.get('groups',[]))],key=lambda x:x['timestamp_ns'])
p=select('producer','model_step_host_start',producer);pr=select('producer','model_step_host_return',producer);d=select('consumer','model_step_host_start',consumer);dr=select('consumer','model_step_host_return',consumer);send=select('producer','send_kv_caches_and_hidden_states_host_start',producer);sendret=select('producer','send_kv_caches_and_hidden_states_host_return',producer);recv=select('consumer','recv_kv_caches_and_hidden_states_host_start',consumer);recvret=select('consumer','recv_kv_caches_and_hidden_states_host_return',consumer)
assert (len(p),len(pr),len(d),len(dr),len(send),len(sendret),len(recv),len(recvret))==(1,1,64,64,1,1,1,1)
assert recvret[0]['kv_bypass'] is True
assert r['server_arrival'][0]['timestamp_ns']<=p[0]['timestamp_ns']<=send[0]['timestamp_ns']<=sendret[0]['timestamp_ns']<=pr[0]['timestamp_ns']<=r['prefill_response'][0]['timestamp_ns']<=r['decode_send'][0]['timestamp_ns']<=d[0]['timestamp_ns']<=recv[0]['timestamp_ns']<=recvret[0]['timestamp_ns']<=dr[0]['timestamp_ns']<=dr[-1]['timestamp_ns']<=r['server_complete'][0]['timestamp_ns']<=c['client_complete_ns']
origin=r['server_arrival'][0]['timestamp_ns'];timeline=sorted(routes+events,key=lambda x:x['timestamp_ns']);assert all(x['clock_id']=='CLOCK_MONOTONIC' for x in timeline)
(out/'events.jsonl').write_text(''.join(json.dumps(dict(e,relative_s=(e['timestamp_ns']-origin)/1e9),separators=(',',':'))+'\n' for e in timeline))
result={'status':'streaming_host_timeline_observed','router_id':c['router_id'],'producer_worker_id':producer,'consumer_worker_id':consumer,'input_tokens':512,'output_tokens':64,'producer_steps':len(p),'consumer_steps':len(d),'kv_bypass':True,'server_e2e_s':(r['server_complete'][0]['timestamp_ns']-origin)/1e9,'client_e2e_s':(c['client_complete_ns']-c['client_send_ns'])/1e9,'limitations':['Host events and worker return do not prove GPU operation completion or exact KVReady','This is an instrumented repeated request, not the original calibration record','No network transfer start/end timestamps, queue cause attribution, or quantified instrumentation overhead','Not validation or a frozen fee']}
(out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
