"""Audit a same-input synchronized diagnostic; not a production E2E run."""
import glob,hashlib,json,pathlib,sys
root=pathlib.Path(sys.argv[1]);original=pathlib.Path(sys.argv[2]);out=pathlib.Path(sys.argv[3]);out.mkdir(parents=True,exist_ok=False)
ref=json.loads(original.read_text());response=json.loads((root/'measured.json').read_text());route=[json.loads(x) for x in (root/'service/router-events.jsonl').read_text().splitlines()]
assert len(route)==2 and response['status']==200 and response['response']['usage']['prompt_tokens']==512 and response['response']['usage']['completion_tokens']==64
r=route[-1];assert r['decode_id']==response['response']['id'] and r['prefill_status']==r['decode_status']==200
raw=(json.dumps(ref['input_ids'],separators=(',',':'))).encode();assert len(ref['input_ids'])==512 and hashlib.sha256(raw).hexdigest()==ref['input_sha256']
events=[]
for f in (root/'service').glob('compute-events-*.jsonl'):
 for line in f.read_text().splitlines():
  e=json.loads(line)
  if e.get('event')=='model_step':events.append(e)
def hits(rid):return sorted((x for x in events if rid+'-0' in x.get('request_ids_to_seq_ids',{})),key=lambda x:x['host_start_ns'])
prefill=hits(r['prefill_id']);decode=hits(r['decode_id']);assert len(prefill)==1 and len(decode)==64
p=prefill[0];d=decode[0];h=d['host_intervals'];assert p['query_lens']==[512] and d['query_lens']==[512] and h['kv_bypass'] is True
assert all(x['query_lens']==[1] for x in decode[1:])
for name in ('logits','sampler'):assert name in p['host_intervals'] and name in h
assert r['arrival_ns']<=p['host_start_ns']<=p['host_after_sync_ns']<=r['prefill_done_ns']<=r['decode_submit_ns']<=d['host_start_ns']<=h['kv_ready_sync_ns'][1]<=d['host_after_sync_ns']<=r['decode_done_ns']<=r['router_complete_ns']
assert h['kv_ready_bound_ns'][0]<=h['kv_ready_sync_ns'][1]==h['kv_ready_bound_ns'][1]
result={'status':'same_input_instrumented_diagnostic','input_sha256':ref['input_sha256'],'input_tokens':512,'output_tokens':64,'router':r,'producer_model_steps':len(prefill),'consumer_kv_bypass_prompt_steps':1,'consumer_subsequent_decode_steps':len(decode)-1,'producer_first_step':p,'consumer_first_step':d,'consumer_subsequent_steps':[{'host_start_ns':x['host_start_ns'],'host_after_sync_ns':x['host_after_sync_ns'],'seq_lens':x['seq_lens'],'query_lens':x['query_lens']} for x in decode[1:]],'limitations':['Separate repeated request, not the original calibration request','Device synchronizations and hooks perturb timing; cannot compare as production E2E','KVReady is an interval bounded by receive and post-install synchronize, not exact timestamp','Non-stream diagnostic router completion follows full backend response read, before its own response is sent','Sampling occurs at both endpoints but no sampled-token identity equivalence is established']}
(out/'audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ('producer_first_step','consumer_first_step','consumer_subsequent_steps')},indent=2))
