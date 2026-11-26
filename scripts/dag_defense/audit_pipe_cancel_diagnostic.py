"""Audit recorded client cancellation and subsequent host observations."""
import json,pathlib,sys
root=pathlib.Path(sys.argv[1]);out=pathlib.Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=False)
assert (root/'exit').read_text().strip()=='0';client=json.loads((root/'warmup.json').read_text());assert client['status']=='client_cancelled_after_first' and client['http_status']==200
routes=[json.loads(x) for x in (root/'service/router-events.jsonl').read_text().splitlines() if json.loads(x)['request_id']==client['router_id']];events=[x['event'] for x in routes];assert events.count('server_arrival')==1 and events.count('server_error')==1 and 'server_complete' not in events
error=next(x for x in routes if x['event']=='server_error');assert error['stage']=='decode_stream' and error['error']=='CancelledError';assert client['send_ns']<=client['first_token_ns']<=client['client_end_ns']<=error['timestamp_ns']
samples=[json.loads(x) for x in (root/'probe/observations.jsonl').read_text().splitlines()];assert len(samples)==4
by={}
for f in (root/'observer').glob('*.jsonl'):
 rows=[json.loads(x) for x in f.read_text().splitlines()];role=rows[0]['role'];assert role not in by;by[role]=rows
assert set(by)=={'producer','consumer'};joined=[]
for s in samples:
 assert s['router']['inflight']==0 and s['router']['unresolved_errors']==1;row={'monotonic_ns':s['monotonic_ns'],'roles':{}}
 for role,endpoint in [('producer','prefill'),('consumer','decode')]:
  g=s['servers'][endpoint]['gauges'];assert len(g)==5 and all(v==0 for v in g.values());prior=[x for x in by[role] if x['monotonic_ns']<=s['monotonic_ns']];assert prior;x=prior[-1];age=(s['monotonic_ns']-x['monotonic_ns'])/1e9
  assert age<=1.5 and x['lock_acquired'] and x['queue_items']==x['buffer_bytes']==x['pipe_buffer_bytes']==0 and not any(x['active'].values()) and not any(x['pipe_active'].values())
  kind='insert' if role=='producer' else 'select';assert x['counts'][kind+'_started']==x['counts'][kind+'_completed']==1
  pc=x['pipe_counts'];assert pc['send_started']==pc['send_completed'] and pc['recv_started']==pc['recv_completed']
  row['roles'][role]={'pid':x['pid'],'snapshot_age_s':age,'counts':x['counts'],'pipe_counts':pc}
 joined.append(row)
probe=json.loads((root/'probe/summary.json').read_text());assert probe['status']=='observed_busy_or_error' and int((root/'probe-exit').read_text())==1
result={'status':'client_disconnect_observed_host_quiescent_but_error_unresolved','client':client,'router_error':error,'samples':joined,'limitations':['Client cancellation occurred after first token, not before Prefill or during KV transfer','Host observations and zero gauges do not prove GPU work complete','Router error remains unresolved; readiness probe correctly rejects the state','Crash and other timeout paths are untested; not formal validation']}
(out/'audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
