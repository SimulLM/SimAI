"""Join concurrent warmup, metrics and connector host snapshots; not a GPU idle proof."""
import json,pathlib,sys
root=pathlib.Path(sys.argv[1]);out=pathlib.Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=False)
assert (root/'exit').read_text().strip()=='0';warm=json.loads((root/'warmup.json').read_text());assert len(warm)==4 and len({x['router_id'] for x in warm})==4
assert all(x['status']==200 and x['done'] and x['usage']['prompt_tokens']==512 and x['usage']['completion_tokens']==8 for x in warm)
routes=[json.loads(x) for x in (root/'service/router-events.jsonl').read_text().splitlines()]
for w in warm:
 e=[x['event'] for x in routes if x['request_id']==w['router_id']];assert e.count('server_arrival')==e.count('server_complete')==1
samples=[json.loads(x) for x in (root/'probe/observations.jsonl').read_text().splitlines()];assert len(samples)==4
by={}
for file in (root/'observer').glob('*.jsonl'):
 rows=[json.loads(x) for x in file.read_text().splitlines()];role=rows[0]['role'];assert role not in by and all(x['role']==role and x['pid']==rows[0]['pid'] for x in rows);by[role]=rows
assert set(by)=={'producer','consumer'};joined=[]
for s in samples:
 assert s['router']['status']=='observed' and not s['router']['inflight'] and not s['router']['unresolved_errors'];item={'sample':s['sample'],'monotonic_ns':s['monotonic_ns'],'roles':{}}
 for role,server in [('producer','prefill'),('consumer','decode')]:
  gauges=s['servers'][server].get('gauges',{});assert len(gauges)==5 and all(v==0 for v in gauges.values())
  eligible=[x for x in by[role] if x['monotonic_ns']<=s['monotonic_ns']];assert eligible;x=eligible[-1];age=(s['monotonic_ns']-x['monotonic_ns'])/1e9
  assert age<=1.5 and x['lock_acquired'] and x['queue_items']==0 and x['buffer_bytes']==0 and not any(x['active'].values())
  assert x['pipe_buffer_bytes']==0 and not any(x['pipe_active'].values())
  counts=x['counts'];required='insert' if role=='producer' else 'select';assert counts[required+'_started']==counts[required+'_completed']==4
  pc=x['pipe_counts'];assert pc['send_started']==pc['send_completed'] and pc['recv_started']==pc['recv_completed'] and pc['send_completed']>0 and pc['recv_completed']>0
  item['roles'][role]={'pid':x['pid'],'age_s':age,'counts':counts,'pipe_counts':pc,'queue_items':x['queue_items'],'pipe_buffer_bytes':x['pipe_buffer_bytes']}
 joined.append(item)
result={'status':'concurrent_host_idle_observations_consistent','warmup_requests':4,'samples':joined,'probe_exit':int((root/'probe-exit').read_text()),'limitations':['Observer thread and monkey patches may alter timing','Completed host calls and empty host buffers do not prove asynchronous GPU operations completed','Only four successful concurrent requests; timeout, failure and interrupted transfer cleanup not tested','Gauge sampling can miss transient states and readiness is not certified','No formal validation was run']}
(out/'audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
