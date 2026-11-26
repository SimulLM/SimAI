"""Check token IDs emitted by real producer and consumer for one fixed input."""
import hashlib,json,pathlib,re,sys
root=pathlib.Path(sys.argv[1]);ref=pathlib.Path(sys.argv[2]);out=pathlib.Path(sys.argv[3]);out.mkdir(parents=True,exist_ok=False)
assert (root/'exit').read_text().strip()=='0';data=json.loads((root/'responses.json').read_text());source=json.loads(ref.read_text());raw=json.dumps(source['input_ids'],separators=(',',':')).encode();assert hashlib.sha256(raw).hexdigest()==source['input_sha256'] and len(source['input_ids'])==512
assert [x['stage'] for x in data]==['warmup','measured'];result=[]
for row in data:
 p=row['prefill'];d=row['decode'];assert p['status']==d['status']==200 and p['send_ns']<=p['complete_ns']<=d['send_ns']<=d['complete_ns']
 assert p['body']['usage']['prompt_tokens']==d['body']['usage']['prompt_tokens']==512 and p['body']['usage']['completion_tokens']==1 and d['body']['usage']['completion_tokens']==64
 pt=p['body']['choices'][0]['logprobs']['tokens'];dt=d['body']['choices'][0]['logprobs']['tokens'];assert len(pt)==1 and len(dt)==64 and all(re.fullmatch(r'token_id:[0-9]+',x) for x in pt+dt)
 result.append({'stage':row['stage'],'producer_id':p['body']['id'],'consumer_id':d['body']['id'],'producer_token':pt[0],'consumer_first_token':dt[0],'same':pt[0]==dt[0],'consumer_token_count':len(dt),'producer_send_ns':p['send_ns'],'producer_complete_ns':p['complete_ns'],'consumer_send_ns':d['send_ns'],'consumer_complete_ns':d['complete_ns']})
summary={'status':'observed_token_identity','input_sha256':source['input_sha256'],'rows':result,'limitations':['One fixed input repeated twice; equality is not a guarantee for other inputs or nondeterministic settings','Non-stream direct endpoint requests with logprobs enabled; not formal E2E or router timing','This test alone does not timestamp transport or GPU KVReady; separate instrumented trace supplies those bounds']};(out/'audit.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
