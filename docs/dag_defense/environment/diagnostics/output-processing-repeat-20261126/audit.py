import json,pathlib,statistics,math
p=pathlib.Path(__file__).parent
assert (p/'exit').read_text().strip()=='0'
clients=json.loads((p/'client.json').read_text()); assert len(clients)==40
byid={}
for f in (p/'service/events').glob('*.jsonl'):
 for line in f.open():
  e=json.loads(line)
  if e.get('role')=='consumer':
   for g in e.get('groups',[]): byid.setdefault(g['request_id'],[]).append(e)
routes={}
for line in (p/'service/router-events.jsonl').open():
 e=json.loads(line); routes.setdefault(e['request_id'],{})[e['event']]=e
rows=[]
for c in clients:
 assert c['http_status']==200 and c['done'] and c['usage']['prompt_tokens']==512 and c['usage']['completion_tokens']==64
 rid=c['backend_id']+'-0'; es=byid[rid]
 def times(name): return sorted(e['timestamp_ns'] for e in es if e['event']==name)
 starts,ends,ps,pe=[times(n) for n in ('model_step_host_start','model_step_host_return','output_process_host_start','output_process_host_return')]
 assert len(starts)==len(ends)==len(ps)==len(pe)==64,(rid,len(starts),len(ends),len(ps),len(pe))
 assert all(starts[i]<=ends[i]<=ps[i]<=pe[i] and (i==63 or pe[i]<=starts[i+1]) for i in range(64)),rid
 r=routes[c['router_id']]; assert r['decode_mapping']['backend_request_id']==c['backend_id']
 final=r['server_final_choice_observed']['timestamp_ns']; complete=r['server_complete']['timestamp_ns']; assert pe[-1]<=final<=complete
 rows.append(dict(stage=c['stage'],request_id=c['router_id'],backend_id=rid,last_process_start_ns=ps[-1],last_process_return_ns=pe[-1],router_final_choice_ns=final,router_complete_ns=complete,last_process_ms=(pe[-1]-ps[-1])/1e6,return_to_choice_ms=(final-pe[-1])/1e6,choice_to_complete_ms=(complete-final)/1e6))
measured=rows[10:]
def summary(k):
 a=sorted(x[k] for x in measured);return {'n':len(a),'median_ms':statistics.median(a),'min_ms':a[0],'max_ms':a[-1],'p95_nearest_rank_ms':a[math.ceil(.95*len(a))-1]}
out={'warmup':10,'measured':30,'all_requests_validated':len(rows),'intervals':{k:summary(k) for k in ('last_process_ms','return_to_choice_ms','choice_to_complete_ms')},'limitations':['same instrumented service session; not independent E2E repetitions','host return does not prove GPU completion','logging perturbs timing','intervals may overlap existing simulator CPU costs; do not add without scope parity','not formal validation'], 'requests':rows}
(p/'audit.json').write_text(json.dumps(out,indent=2)+'\n'); print(json.dumps({k:v for k,v in out.items() if k!='requests'},indent=2))
