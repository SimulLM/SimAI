"""Compare real same-host client and router boundaries in calibration only."""
import collections,csv,json,math,pathlib,statistics,sys
runs=pathlib.Path(sys.argv[1]);out=pathlib.Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=False);rows=[]
for mode in ('serial','concurrent'):
 root=runs/f'calibration-{mode}-independent-20261126'
 for rep in range(3):
  clients=[json.loads(x) for x in (root/f'client-{rep}/requests.jsonl').read_text().splitlines()];events=collections.defaultdict(lambda:collections.defaultdict(list))
  for line in (root/f'server-{rep}/router-events.jsonl').read_text().splitlines():
   e=json.loads(line);events[e['request_id']][e['event']].append(e)
  selected=[x for x in clients if not x['warmup']];assert len(selected)==32
  for c in selected:
   assert c['status']==200 and c['done'] and c['usage']['prompt_tokens']==512 and c['usage']['completion_tokens']==64
   ev=events[c['router_id']];assert all(len(ev[k])==1 for k in ('server_arrival','server_first_token','server_complete','decode_mapping'))
   a=ev['server_arrival'][0];ft=ev['server_first_token'][0];z=ev['server_complete'][0];assert all(x['clock_id']=='CLOCK_MONOTONIC' for x in (a,ft,z));assert ev['decode_mapping'][0]['backend_request_id']==c['decode_id']
   assert c['send_ns']<=a['timestamp_ns']<=ft['timestamp_ns']<=c['first_token_ns']<=z['timestamp_ns']<=c['complete_ns']
   rows.append({'mode':mode,'repeat':rep,'router_id':c['router_id'],'client_send_ns':c['send_ns'],'server_arrival_ns':a['timestamp_ns'],'server_first_token_ns':ft['timestamp_ns'],'client_first_token_ns':c['first_token_ns'],'server_complete_ns':z['timestamp_ns'],'client_complete_ns':c['complete_ns'],'send_to_arrival_ms':(a['timestamp_ns']-c['send_ns'])/1e6,'first_forward_ms':(c['first_token_ns']-ft['timestamp_ns'])/1e6,'completion_forward_ms':(c['complete_ns']-z['timestamp_ns'])/1e6,'server_e2e_ms':(z['timestamp_ns']-a['timestamp_ns'])/1e6})
assert len(rows)==192
with (out/'requests.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
groups=[]
for mode in ('serial','concurrent'):
 for rep in range(3):
  group=[x for x in rows if x['mode']==mode and x['repeat']==rep];metrics={}
  for key in ('send_to_arrival_ms','first_forward_ms','completion_forward_ms','server_e2e_ms'):
   v=sorted(x[key] for x in group);metrics[key]={'median':statistics.median(v),'p95_nearest_rank':v[math.ceil(.95*len(v))-1],'max':v[-1]}
  groups.append({'mode':mode,'repeat':rep,'count':len(group),'metrics':metrics})
result={'status':'calibration_client_router_clock_boundaries_observed','requests':192,'groups':groups,'limitations':['Router server_complete is stream consumption/forwarding completion, not last GPU completion','Same-host client-server forwarding differences do not measure missing GPU-to-router or backend serialization cost','All requests succeeded; failure and timeout boundaries are not characterized','These are calibration data, not validation and not a fitted fee']};(out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
