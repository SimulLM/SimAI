"""Audit serial instrumented transport windows; host synchronization perturbs timing."""
import json,pathlib,sys
root=pathlib.Path(sys.argv[1]);out=pathlib.Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=False)
assert (root/'exit').read_text().strip()=='0';client=json.loads((root/'client.json').read_text());assert len(client)==2 and client[-1]['stage']=='measured';c=client[-1]
assert c['done'] and c['usage']['prompt_tokens']==512 and c['usage']['completion_tokens']==64
routes=[json.loads(x) for x in (root/'service/router-events.jsonl').read_text().splitlines() if json.loads(x)['request_id']==c['router_id']]
lookup={x['event']:x for x in routes};assert len(lookup)==len(routes);start=lookup['server_arrival']['timestamp_ns'];end=lookup['server_complete']['timestamp_ns'];consumer=lookup['decode_mapping']['backend_request_id']+'-0';producer=lookup['prefill_mapping']['backend_request_id']+'-0';assert c['backend_id']+'-0'==consumer
all_events=[]
for file in (root/'service/events').glob('*.jsonl'):
 for line in file.read_text().splitlines():
  x=json.loads(line)
  if start<=x['timestamp_ns']<=end:all_events.append(x)
def find(role,name):return sorted([x for x in all_events if x['role']==role and x['event']==name],key=lambda x:x['timestamp_ns'])
ps=find('producer','transport__send_impl_host_start');pc=find('producer','transport__send_impl_device_sync_complete');cr=find('consumer','transport__recv_impl_host_return');cc=find('consumer','transport__recv_impl_device_sync_complete');expected=[4096,2048,134217728,134217728,4194304]
assert len(ps)==len(pc)==len(cr)==len(cc)==5 and [x['bytes'] for x in ps]==expected and [x['bytes'] for x in cr]==expected
for i in range(5):assert ps[i]['timestamp_ns']<=pc[i]['timestamp_ns'] and cr[i]['timestamp_ns']<=cc[i]['timestamp_ns']
installs=[x for x in find('consumer','kv_install_api_start') if any(g['request_id']==consumer for g in x.get('groups',[]))];done=[x for x in find('consumer','kv_install_sync_complete') if any(g['request_id']==consumer for g in x.get('groups',[]))];assert len(installs)==32 and len(done)==1
first_step=[x for x in find('consumer','model_step_host_start') if any(g['request_id']==consumer for g in x.get('groups',[]))];assert len(first_step)==64
assert cc[-1]['timestamp_ns']<=installs[0]['timestamp_ns']<=installs[-1]['timestamp_ns']<=done[0]['timestamp_ns']<=lookup['server_first_token']['timestamp_ns']<=end
records=sorted([x for x in all_events if x['event'].startswith(('transport_','kv_install'))],key=lambda x:x['timestamp_ns']);assert all(x['clock_id']=='CLOCK_MONOTONIC' for x in records)
(out/'events.jsonl').write_text(''.join(json.dumps(dict(x,relative_s=(x['timestamp_ns']-start)/1e9),separators=(',',':'))+'\n' for x in records))
result={'status':'serial_synchronized_transport_diagnostic','router_id':c['router_id'],'producer_worker_id':producer,'consumer_worker_id':consumer,'producer_tensor_bytes':expected,'total_producer_tensor_bytes':sum(expected),'kv_install_calls':len(installs),'first_producer_send_host_s':(ps[0]['timestamp_ns']-start)/1e9,'last_producer_send_sync_s':(pc[-1]['timestamp_ns']-start)/1e9,'last_consumer_recv_sync_s':(cc[-1]['timestamp_ns']-start)/1e9,'last_install_api_start_s':(installs[-1]['timestamp_ns']-start)/1e9,'install_sync_complete_s':(done[0]['timestamp_ns']-start)/1e9,'server_first_token_s':(lookup['server_first_token']['timestamp_ns']-start)/1e9,'server_e2e_s':(end-start)/1e9,'limitations':['One serial request: background transport operations are associated by exclusive time window, not carried request ID','Each tensor uses explicit device-wide synchronization; time and overlap differ from noninstrumented service','API start and sync end bound operations but are not exact GPU start or completion timestamps','Bytes exclude control messages, metadata and transport framing','This is diagnostic, not production E2E, freeze or validation']}
(out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
