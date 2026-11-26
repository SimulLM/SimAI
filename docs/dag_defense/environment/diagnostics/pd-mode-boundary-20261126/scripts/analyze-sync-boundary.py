import collections,json,re,statistics,sys
from pathlib import Path
base=Path(sys.argv[1]); client=sys.argv[2]; output=Path(sys.argv[3]); rows=[json.loads(x) for x in (base/client/'requests.jsonl').read_text().splitlines()];pid=re.search(r'Started engine process with PID (\d+)',(base/'decode.log').read_text()).group(1);events=collections.defaultdict(list)
for line in (base/f'compute-events-{pid}.jsonl').read_text().splitlines():
 e=json.loads(line)
 if e.get('event')=='model_step':
  for rid in e.get('request_ids_to_seq_ids',{}):events[rid].append(e)
patterns=collections.Counter(); records=[]
for r in rows:
 rid=r['backend_request_id']+'-0';es=events[rid];p=sum(all(q>1 for q in e['query_lens']) for e in es); d=len(es)-p;after=sum(e['host_after_sync_ns']>r['end_ns'] for e in es); patterns[(p,d,after)]+=1;records.append({'decode_id':rid,'prefill_calls':p,'decode_calls':d,'host_sync_after_client':after})
assert len(rows)==len({r['backend_request_id'] for r in rows}) and all(r['status']==200 and r['usage']['completion_tokens']==64 for r in rows)
assert patterns=={(1,63,0):len(rows)},patterns
out={'status':'diagnostic_passed','requests':len(rows),'patterns':[{'prefill_bypass_calls':p,'decode_calls':d,'host_sync_after_client':a,'requests':n} for (p,d,a),n in patterns.items()],'formal_validation':False,'records':records,'limitations':['synchronized diagnostic may perturb timing','host sync and client completion are not equivalent to GPU completion timestamp','consumer decode ID mapping does not itself map producer ID']};output.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k!='records'},indent=2))
