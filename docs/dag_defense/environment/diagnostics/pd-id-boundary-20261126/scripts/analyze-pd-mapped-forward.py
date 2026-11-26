"""Join consumer model steps to backend completion IDs, not time windows."""
import collections,json,statistics
from pathlib import Path
base=Path('/root/autodl-tmp/dag-handoff/runs/pd-mapped-forward-20261126'); rows=[json.loads(x) for x in (base/'client/requests.jsonl').read_text().splitlines()]; events=collections.defaultdict(list)
for line in (base/'compute-events-77637.jsonl').read_text().splitlines():
 e=json.loads(line)
 if e.get('event')=='model_step':
  for rid in e.get('request_ids_to_seq_ids',{}): events[rid].append(e)
patterns=collections.Counter(); post=[]; records=[]
for r in rows:
 rid=r['backend_request_id']+'-0'; es=events[rid]; phases=''.join('P' if all(q>1 for q in e['query_lens']) else 'D' for e in es); after=[e for e in es if e['host_after_sync_ns']>r['end_ns']]; starts_after=sum(e['host_start_ns']>r['end_ns'] for e in es)
 patterns[(phases,len(after),starts_after)]+=1
 for e in after:post.append((e['host_after_sync_ns']-r['end_ns'])/1e6)
 records.append({'decode_request_id':rid,'wave_batch':r['batch'],'wave':r['wave'],'phases':phases,'client_complete_ns':r['end_ns'],'steps':len(es),'host_sync_after_client':len(after),'step_starts_after_client':starts_after})
assert len(rows)==50 and len({r['backend_request_id'] for r in rows})==50 and all(r['status']==200 and r['usage']['completion_tokens']==2 for r in rows)
assert patterns=={('PDD',1,0):50}
summary={'status':'diagnostic_passed','request_count':len(rows),'input_tokens':512,'output_tokens':2,'clock':'CLOCK_MONOTONIC','id_mapping':'consumer ModelInputForGPU.request_ids_to_seq_ids joined to client response backend id with -0 suffix','patterns':[{'phases':k[0],'host_sync_after_client':k[1],'step_starts_after_client':k[2],'requests':v} for k,v in patterns.items()],'post_client_host_sync_ms':{'median':statistics.median(post),'min':min(post),'max':max(post)},'interpretation':'Each request had consumer prefill-bypass and two decode model step invocations; the final invocation started before the client received its nonstream response but its host-side post-step synchronization completed after client receipt. The CUDA event has duration but no host-anchored GPU completion timestamp: do not infer that GPU finished after the response. Diagnostic synchronization may perturb execution.','formal_validation':False,'records':records}
(base/'id-join-summary.json').write_text(json.dumps(summary,indent=2)+'\n'); print(json.dumps({k:v for k,v in summary.items() if k!='records'},indent=2))
