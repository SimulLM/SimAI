import collections,json,pathlib,statistics,math,csv
root=pathlib.Path(__file__).parent
assert (root/'exit').read_text().strip()=='0'
clients=json.loads((root/'client.json').read_text());assert len(clients)==25
routes=collections.defaultdict(dict)
for line in (root/'service/router-events.jsonl').open():
 x=json.loads(line);d=routes[x['request_id']];assert x['event'] not in d;d[x['event']]=x
workers=collections.defaultdict(list)
for f in (root/'service/events').glob('*.jsonl'):
 for line in f.open():
  x=json.loads(line)
  for g in x.get('groups',[]):workers[g['request_id']].append(x)
rows=[]
for c in clients:
 assert c['done'] and c['usage']['prompt_tokens']==512 and c['usage']['completion_tokens']==64
 r=routes[c['router_id']];rid=c['backend_id']+'-0';assert r['decode_mapping']['backend_request_id']==c['backend_id']
 e=workers[rid]
 def one(name):
  es=[x for x in e if x['event']==name];assert len(es)==1,(rid,name,len(es));return es[0]['timestamp_ns']
 def steps(name):return sorted(x['timestamp_ns'] for x in e if x['event']==name)
 st=steps('model_step_host_start');end=steps('model_step_host_return');assert len(st)==len(end)==64
 recv=one('recv_kv_caches_and_hidden_states_host_start');ret=one('recv_kv_caches_and_hidden_states_host_return')
 arrival=r['server_arrival']['timestamp_ns'];first=r['server_first_token']['timestamp_ns'];last=r['server_final_choice_observed']['timestamp_ns'];done=r['server_complete']['timestamp_ns']
 assert arrival<=st[0]<=recv<=ret<=end[0]<=first<=end[-1]<=last<=done<=c['client_complete_ns']
 assert r['server_final_choice_observed']['finish_reasons']==['length'] and r['server_final_choice_observed']['completion_tokens']==64
 rows.append({'stage':c['stage'],'router_id':c['router_id'],'backend_id':rid,'arrival_ns':arrival,'first_step_start_ns':st[0],'receive_start_ns':recv,'receive_return_ns':ret,'first_step_return_ns':end[0],'router_first_ns':first,'last_step_return_ns':end[-1],'final_choice_ns':last,'completion_ns':done,'receive_host_ms':(ret-recv)/1e6,'after_receive_to_first_step_return_ms':(end[0]-ret)/1e6,'last_host_to_final_choice_ms':(last-end[-1])/1e6,'final_choice_to_completion_ms':(done-last)/1e6,'server_e2e_ms':(done-arrival)/1e6})
with (root/'analysis.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
meas=rows[5:];stats={}
for key in ('receive_host_ms','after_receive_to_first_step_return_ms','last_host_to_final_choice_ms','final_choice_to_completion_ms','server_e2e_ms'):
 vals=sorted(x[key] for x in meas);stats[key]={'median':statistics.median(vals),'min':min(vals),'max':max(vals),'p95':vals[math.ceil(.95*len(vals))-1]}
(root/'analysis.json').write_text(json.dumps({'warmup':5,'measured':len(meas),'stats_ms':stats,'limitations':['host event returns do not establish GPU completion or exact KVReady','logging perturbs timing','same session repeated requests are not independent sessions','not formal validation and not a frozen fee']},indent=2)+'\n');print(json.dumps(stats,indent=2))
