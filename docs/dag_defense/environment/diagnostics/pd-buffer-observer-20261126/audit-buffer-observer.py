"""Join real router/metrics samples to same-process connector observations."""
import json,pathlib,sys
p=pathlib.Path(sys.argv[1]);out=pathlib.Path(sys.argv[2]);warm=json.loads((p/'warmup.json').read_text());samples=[json.loads(x) for x in (p/'probe/observations.jsonl').read_text().splitlines()];events=[json.loads(x) for x in (p/'service/router-events.jsonl').read_text().splitlines()];rid=warm['router_id']; names=[x['event'] for x in events if x['request_id']==rid]
if not(warm['status']==200 and warm['done'] and warm['usage']['prompt_tokens']==512 and warm['usage']['completion_tokens']==64 and names.count('server_arrival')==names.count('server_complete')==1):raise ValueError('warmup request invalid')
files=list((p/'observer').glob('*.jsonl'));by={}
for f in files:
 rows=[json.loads(x) for x in f.read_text().splitlines()];role=rows[0]['role']
 if role in by or any(x['role']!=role or x['pid']!=rows[0]['pid'] for x in rows):raise ValueError('ambiguous observer')
 by[role]=rows
if set(by)!={'producer','consumer'} or len(samples)!=4:raise ValueError('missing observer or gauge samples')
joined=[]
for s in samples:
 item={'sample':s['sample'],'monotonic_ns':s['monotonic_ns'],'roles':{}}
 if s['router']['inflight'] or s['router']['unresolved_errors']:raise ValueError('router not idle')
 for role,server in [('producer','prefill'),('consumer','decode')]:
  g=s['servers'][server].get('gauges',{})
  if len(g)!=5 or any(v is None or v!=0 for v in g.values()):raise ValueError('gauge missing or busy')
  eligible=[r for r in by[role] if r['monotonic_ns']<=s['monotonic_ns']]
  if not eligible:raise ValueError('no prior observer')
  r=eligible[-1];age=(s['monotonic_ns']-r['monotonic_ns'])/1e9;counts=r['counts'];required='insert' if role=='producer' else 'select'
  if age>1.5 or not r['lock_acquired'] or r['queue_items']!=0 or r['buffer_bytes']!=0 or any(r['active'].values()) or counts[required+'_started']!=1 or counts[required+'_completed']!=1:raise ValueError(f'unobserved/busy connector {role} sample {s["sample"]}')
  item['roles'][role]={'pid':r['pid'],'age_s':age,'queue_items':r['queue_items'],'buffer_bytes':r['buffer_bytes'],'active':r['active'],'counts':counts}
 joined.append(item)
result={'status':'diagnostic_observations_consistent','request_id':rid,'samples':joined,'limitations':['Observation thread and monkey patch alter the process; effect on timing is not measured','Host send/receive call completion and empty queue do not prove all asynchronous device operations complete','A 0.5 second sample can miss transient states; counters cover insert/select calls but not every device task','No timeout/failure cleanup case or concurrent workload was tested','No formal readiness or validation claim']};out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
