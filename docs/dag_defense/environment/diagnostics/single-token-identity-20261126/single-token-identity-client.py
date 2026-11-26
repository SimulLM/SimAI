import hashlib,json,pathlib,sys,time,urllib.request
out=pathlib.Path(sys.argv[1]);ref=json.loads(pathlib.Path(sys.argv[2]).read_text());ids=ref['input_ids'];assert hashlib.sha256(json.dumps(ids,separators=(',',':')).encode()).hexdigest()==ref['input_sha256']
base={'model':'/root/autodl-tmp/models/Llama-2-7b-hf','prompt':ids,'temperature':0,'top_p':1,'seed':0,'ignore_eos':True,'stream':False,'logprobs':1,'return_tokens_as_token_ids':True}
def call(port,max_tokens,min_tokens):
 body=dict(base,max_tokens=max_tokens,min_tokens=min_tokens);request=urllib.request.Request(f'http://127.0.0.1:{port}/v1/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'});start=time.monotonic_ns()
 with urllib.request.urlopen(request,timeout=180) as res: data=json.load(res);status=res.status
 return {'send_ns':start,'complete_ns':time.monotonic_ns(),'status':status,'body':data}
rows=[]
for stage in ('warmup','measured'):
 pre=call(18100,1,0);dec=call(18200,64,64);rows.append({'stage':stage,'prefill':pre,'decode':dec})
(out/'responses.json').write_text(json.dumps(rows,indent=2)+'\n')
for row in rows:
 p=row['prefill'];d=row['decode'];assert p['status']==d['status']==200 and p['body']['usage']['completion_tokens']==1 and d['body']['usage']['completion_tokens']==64
 for side,n in ((p,1),(d,64)):
  tokens=side['body']['choices'][0]['logprobs']['tokens'];assert len(tokens)==n and all(t.startswith('token_id:') for t in tokens)
