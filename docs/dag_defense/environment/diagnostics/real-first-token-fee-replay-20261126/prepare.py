import json,pathlib,csv,hashlib
base=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/pd-kv-ready-bound-20261126');out=pathlib.Path(__file__).parent
req=[json.loads(x) for x in (base/'coverage/requests.jsonl').read_text().splitlines()];route={x['decode_id']:x for x in map(json.loads,(base/'router-events.jsonl').read_text().splitlines()) if x.get('decode_id')};selected=[x for x in req if x['length']==1024 and x['batch']==4 and x['wave']==10];assert len(selected)==4 and all(not x['warmup'] and x['status']==200 and x['usage']['completion_tokens']==8 for x in selected)
a=sorted([(route[x['backend_request_id']]['arrival_ns'],x) for x in selected]);origin=a[0][0];mapping=[]
with (out/'trace.csv').open('w',newline='') as f:
 w=csv.writer(f);w.writerow(('arrived_at','num_prefill_tokens','num_decode_tokens'))
 for i,(t,x) in enumerate(a):w.writerow(((t-origin)/1e9,1024,8));mapping.append({'sim_id':i,'router_id':route[x['backend_request_id']]['router_id'],'backend_id':x['backend_request_id'],'arrival_ns':t})
sumfile=pathlib.Path('/root/autodl-tmp/SimAI-handoff/docs/dag_defense/environment/diagnostics/pd-first-token-post-kv-20261126/summary.json');s=json.loads(sumfile.read_text());fees={}
for x in s['groups']:
 if x['input_tokens']==1024 and x['requested_concurrency']==4 and x['sample_threshold_met']:fees[f"1024:{x['actual_batch']}"]=x['medians_ms']['post_sync_host_ms']/1000
assert set(fees)=={'1024:1','1024:3'}
(out/'fee.json').write_text(json.dumps(fees,indent=2)+'\n');(out/'input-mapping.json').write_text(json.dumps({'source':'instrumented nonstream profiling, same capture as fee samples, not independent holdout','mapping':mapping,'fees_source_sha256':hashlib.sha256(sumfile.read_bytes()).hexdigest()},indent=2)+'\n');print('prepared actual router arrivals; eligible first-token fee shapes:',fees)
