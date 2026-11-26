"""Compare final consumer host return and streaming completion, not GPU end."""
import collections,csv,json,math,pathlib,statistics,sys
root=pathlib.Path(sys.argv[1]);out=pathlib.Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=False)
assert (root/'exit').read_text().strip()=='0';clients=[json.loads(x) for x in (root/'client.jsonl').read_text().splitlines()];assert len(clients)==120
routes=collections.defaultdict(dict)
for line in (root/'service/router-events.jsonl').read_text().splitlines():
 e=json.loads(line);assert e['event'] not in routes[e['request_id']];routes[e['request_id']][e['event']]=e
steps=collections.defaultdict(list)
for f in (root/'service/events').glob('*.jsonl'):
 for line in f.read_text().splitlines():
  e=json.loads(line)
  if e['role']=='consumer' and e['event']=='model_step_host_return':
   for g in e.get('groups',[]):steps[g['request_id']].append(e)
rows=[]
for c in clients:
 assert c['status']==200 and c['done'] and c['usage']['prompt_tokens']==c['length'] and c['usage']['completion_tokens']==8
 ev=routes[c['router_id']];assert ev['decode_mapping']['backend_request_id']==c['backend_id'];rid=c['backend_id']+'-0';events=sorted(steps[rid],key=lambda x:x['timestamp_ns']);assert len(events)==8
 last=events[-1]['timestamp_ns'];arrival=ev['server_arrival']['timestamp_ns'];complete=ev['server_complete']['timestamp_ns'];assert arrival<=last<=complete<=c['complete_ns']
 rows.append({'length':c['length'],'wave':c['wave'],'warmup':c['warmup'],'router_id':c['router_id'],'consumer_id':rid,'last_step_host_return_ns':last,'server_complete_ns':complete,'client_complete_ns':c['complete_ns'],'host_return_to_server_complete_ms':(complete-last)/1e6,'server_to_client_complete_ms':(c['complete_ns']-complete)/1e6})
with (out/'requests.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
groups=[]
for n in (512,1024,2048):
 warm=[x for x in rows if x['length']==n and x['warmup']];r=[x for x in rows if x['length']==n and not x['warmup']];assert len(warm)==10 and len(r)==30
 metrics={}
 for k in ('host_return_to_server_complete_ms','server_to_client_complete_ms'):
  v=sorted(x[k] for x in r);metrics[k]={'median_ms':statistics.median(v),'p95_ms':v[math.ceil(.95*len(v))-1],'max_ms':v[-1]}
 groups.append({'length':n,'measured':30,'metrics':metrics})
result={'status':'host_boundary_diagnostic','groups':groups,'limitations':['Model-step host return is not a GPU completion timestamp','Per-tensor synchronizations and logging perturb execution; 8 output tokens, serial only','Interval includes any outstanding work and output handling and cannot be added as a pure CPU fee','Not formal validation, original calibration or a frozen cost']};(out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
