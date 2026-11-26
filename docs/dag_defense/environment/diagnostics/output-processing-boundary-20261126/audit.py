import collections,json,pathlib,statistics
p=pathlib.Path(__file__).parent;assert (p/'exit').read_text().strip()=='0'
c=json.loads((p/'client.json').read_text())[-1];assert c['stage']=='measured' and c['http_status']==200
assert c['done'] and c['usage']['prompt_tokens']==512 and c['usage']['completion_tokens']==64
rid=c['backend_id']+'-0';events=[]
for f in (p/'service/events').glob('*.jsonl'):
 for l in f.open():
  e=json.loads(l)
  if any(g['request_id']==rid for g in e.get('groups',[])):events.append(e)
def times(name):return sorted(e['timestamp_ns'] for e in events if e['event']==name and e['role']=='consumer')
starts=times('model_step_host_start');ends=times('model_step_host_return');ps=times('output_process_host_start');pe=times('output_process_host_return');assert len(starts)==len(ends)==len(ps)==len(pe)==64
assert all(starts[i]<=ends[i]<=ps[i]<=pe[i] and (i==63 or pe[i]<=starts[i+1]) for i in range(64))
routes=[json.loads(l) for l in (p/'service/router-events.jsonl').open()];r={x['event']:x for x in routes if x['request_id']==c['router_id']};assert r['decode_mapping']['backend_request_id']==c['backend_id']
final=r['server_final_choice_observed']['timestamp_ns'];complete=r['server_complete']['timestamp_ns'];assert pe[-1]<=final<=complete
result={'request_id':c['router_id'],'backend_id':rid,'consumer_steps':64,'process_intervals':64,'last_step_return_ns':ends[-1],'last_process_start_ns':ps[-1],'last_process_return_ns':pe[-1],'router_final_choice_ns':final,'router_complete_ns':complete,'last_process_duration_ms':(pe[-1]-ps[-1])/1e6,'last_process_return_to_final_choice_ms':(final-pe[-1])/1e6,'final_choice_to_complete_ms':(complete-final)/1e6,'median_process_duration_ms':statistics.median((b-a)/1e6 for a,b in zip(ps,pe)),'limitations':['one measured request, one session','host API return does not prove GPU completion','file event logging perturbs timing','process output may be accounted by simulator CPU profile, but scope parity not proved','not a pure router fee, validation, or freeze']}
(p/'audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
