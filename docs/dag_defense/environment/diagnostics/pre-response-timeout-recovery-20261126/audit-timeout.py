import json,pathlib
p=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/pre-response-timeout-idle-20261126');client=json.loads((p/'client.json').read_text());assert client['status']=='cancelled_after_server_arrival_before_headers' and 'headers_ns' not in client
assert pathlib.Path('/root/autodl-tmp/dag-handoff/pre-response-timeout-idle.exit').read_text().strip()=='0' and (p/'probe-exit').read_text().strip()=='1'
events=[x for x in map(json.loads,(p/'service/router-events.jsonl').open()) if x['request_id']==client['router_id']];names=[x['event'] for x in events];assert names==['server_arrival','prefill_send','prefill_response','prefill_mapping','decode_send','server_error'];assert events[-1]['error']=='CancelledError' and events[2]['timestamp_ns']>client['client_done_ns']
obs=[json.loads(x) for x in (p/'probe/observations.jsonl').open()];assert len(obs)==4;rows=[]
for o in obs:
 assert o['router']['unresolved_errors']>=1
 for role in ('producer','consumer'):
  f=next((p/'observer').glob(role+'-*.jsonl'));x=next(x for x in reversed([json.loads(line) for line in f.open()]) if x['monotonic_ns']<=o['monotonic_ns']);assert (o['monotonic_ns']-x['monotonic_ns'])/1e9<=1.5 and x['lock_acquired'];rows.append({'sample':o['sample'],'role':role,'queue_items':x['queue_items'],'buffer_bytes':x['buffer_bytes'],'counts':x['counts'],'signal_active':x['signal_active']})
assert all(x['queue_items']==1 for x in rows if x['role']=='producer') and all(x['queue_items']==0 for x in rows if x['role']=='consumer')
result={'status':'unsafe_to_reuse_service','client':client,'router_event_sequence':names,'prefill_completed_after_client_cancel_ms':(events[2]['timestamp_ns']-client['client_done_ns'])/1e6,'probe_exit':1,'sampled_state':rows,'limitations':['one cancellation before headers, not every timeout stage','host observer is non-atomic and intrusive','queue item content and device work not proven from gauges alone','stop and restart service before any new run; preserve failure']};pathlib.Path(__file__).with_name('timeout-audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
