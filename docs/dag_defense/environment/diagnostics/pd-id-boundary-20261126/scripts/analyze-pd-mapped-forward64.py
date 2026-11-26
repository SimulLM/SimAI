import collections,json,re,statistics
from pathlib import Path
base=Path('/root/autodl-tmp/dag-handoff/runs/pd-mapped-forward64-20261126'); rows=[json.loads(x) for x in (base/'client/requests.jsonl').read_text().splitlines()]; pid=re.search(r'Started engine process with PID (\d+)',(base/'decode.log').read_text()).group(1); events=collections.defaultdict(list)
for line in (base/f'compute-events-{pid}.jsonl').read_text().splitlines():
 e=json.loads(line)
 if e.get('event')=='model_step':
  for rid in e.get('request_ids_to_seq_ids',{}): events[rid].append(e)
patterns=collections.Counter(); post=[]; records=[]
for r in rows:
 rid=r['backend_request_id']+'-0'; es=events[rid]; p=sum(all(q>1 for q in e['query_lens']) for e in es); d=len(es)-p; after=[e for e in es if e['host_after_sync_ns']>r['end_ns']]; starts_after=sum(e['host_start_ns']>r['end_ns'] for e in es); patterns[(p,d,len(after),starts_after)]+=1; post.extend((e['host_after_sync_ns']-r['end_ns'])/1e6 for e in after);records.append({'decode_request_id':rid,'wave_batch':r['batch'],'wave':r['wave'],'prefill_calls':p,'decode_calls':d,'client_complete_ns':r['end_ns'],'host_sync_after_client':len(after),'step_starts_after_client':starts_after})
assert len(rows)==35 and len({r['backend_request_id'] for r in rows})==35 and all(r['status']==200 and r['usage']['prompt_tokens']==512 and r['usage']['completion_tokens']==64 for r in rows)
assert patterns=={(1,64,1,0):35}
summary={'status':'diagnostic_passed','request_count':35,'input_tokens':512,'output_tokens':64,'clock':'CLOCK_MONOTONIC','id_mapping':'consumer ModelInputForGPU.request_ids_to_seq_ids joined to client response backend id with -0 suffix','patterns':[{'consumer_prefill_bypass_calls':k[0],'decode_calls':k[1],'host_sync_after_client':k[2],'step_starts_after_client':k[3],'requests':v} for k,v in patterns.items()],'post_client_host_sync_ms':{'median':statistics.median(post),'min':min(post),'max':max(post)},'limitations':['The last host sync ends after client receipt, but CUDA event duration is not a host-anchored GPU completion timestamp.','Diagnostic synchronization can perturb timing.','Nonstream client and diagnostic router are not formal E2E.','Sampling and request IDs are diagnostic evidence; this is not the formal streaming router.'],'formal_validation':False,'records':records}
(base/'id-join-summary.json').write_text(json.dumps(summary,indent=2)+'\n'); print(json.dumps({k:v for k,v in summary.items() if k!='records'},indent=2))
