"""Observe vLLM queue/cache gauges and router state; never certify connector idle."""
import argparse,collections,json,math,pathlib,time,urllib.error,urllib.request
from prometheus_client.parser import text_string_to_metric_families
NAMES=('vllm:num_requests_running','vllm:num_requests_waiting','vllm:num_requests_swapped','vllm:gpu_cache_usage_perc','vllm:cpu_cache_usage_perc')
def fetch(url):
 with urllib.request.urlopen(url,timeout=5) as response:body=response.read(4*1024*1024+1).decode()
 if len(body)>4*1024*1024:raise ValueError('metrics response too large')
 found=collections.defaultdict(list)
 for family in text_string_to_metric_families(body):
  for sample in family.samples:
   if sample.name in NAMES:
    if not math.isfinite(sample.value) or sample.value<0:raise ValueError('invalid gauge '+sample.name)
    found[sample.name].append(sample.value)
 return {name:sum(found[name]) if found[name] else None for name in NAMES}
def router_state(path):
 states=collections.defaultdict(list)
 if not path.exists():return {'status':'missing','inflight':None,'unresolved_errors':None}
 for line in path.read_text().splitlines():
  x=json.loads(line);states[x['request_id']].append(x['event'])
 inflight=sum('server_arrival' in ev and not any(e in ev for e in ('server_complete','server_error')) for ev in states.values())
 errors=sum('server_error' in ev for ev in states.values())
 return {'status':'observed','inflight':inflight,'unresolved_errors':errors,'request_ids':len(states)}
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=pathlib.Path,required=True);p.add_argument('--router-events',type=pathlib.Path,required=True);p.add_argument('--samples',type=int,default=3);p.add_argument('--interval',type=float,default=5);p.add_argument('--prefill-url',default='http://127.0.0.1:18100/metrics');p.add_argument('--decode-url',default='http://127.0.0.1:18200/metrics');a=p.parse_args()
 if a.samples<2 or a.interval<=0:raise ValueError('at least two spaced observations required')
 a.output.mkdir(parents=True,exist_ok=False);samples=[]
 for i in range(a.samples):
  entry={'sample':i,'monotonic_ns':time.monotonic_ns(),'router':router_state(a.router_events),'servers':{}}
  for role,url in [('prefill',a.prefill_url),('decode',a.decode_url)]:
   try:entry['servers'][role]={'gauges':fetch(url)}
   except Exception as exc:entry['servers'][role]={'error':type(exc).__name__+': '+str(exc)[:256]}
  samples.append(entry)
  with (a.output/'observations.jsonl').open('a') as f:f.write(json.dumps(entry,separators=(',',':'))+'\n');f.flush()
  if i+1<a.samples:time.sleep(a.interval)
 missing=[];nonzero=[]
 for x in samples:
  if x['router']['status']!='observed':missing.append('router events')
  elif x['router']['inflight'] or x['router']['unresolved_errors']:nonzero.append('router inflight or error')
  for role,s in x['servers'].items():
   if 'error' in s:missing.append(role+' endpoint')
   else:
    for name,value in s['gauges'].items():
     if value is None:missing.append(role+':'+name)
     elif value!=0:nonzero.append(role+':'+name)
 result={'status':'observed_busy_or_error' if nonzero else 'incomplete' if missing else 'gauges_zero_connector_unverified','samples':len(samples),'missing':sorted(set(missing)),'nonzero':sorted(set(nonzero)),'limitations':['Prometheus gauges can be stale and do not expose the SimpleBuffer connector queue','Router terminal or client timeout does not establish that GPU and backend work stopped','Zero gauges cannot alone certify connector empty, warmup cleanup, service identity, or freeze validity','No formal validation was run']};(a.output/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));return 1 if nonzero else 2  # No exit-0 readiness: connector state is unverified.
if __name__=='__main__':raise SystemExit(main())
