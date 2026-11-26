import asyncio,aiohttp,json,pathlib,time,hashlib,sys,random,os
out=pathlib.Path(sys.argv[1]);rep=int(sys.argv[2]);out.mkdir(parents=True,exist_ok=False);model='/root/autodl-tmp/models/Llama-2-7b-hf';random.seed(20261126+rep)
async def main():
 async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=180)) as s:
  for i in range(-4,32):
   rng=random.Random(20261126+rep*1000+i);ids=[1]+[rng.randrange(4,31999) for _ in range(511)];row={'repeat':rep,'index':i,'warmup':i<0,'input_ids':ids,'input_sha256':hashlib.sha256(json.dumps(ids,separators=(',',':')).encode()).hexdigest(),'send_ns':time.monotonic_ns()}; body={'model':model,'prompt':ids,'temperature':0,'top_p':1,'seed':0,'ignore_eos':True,'stream':True,'max_tokens':64,'min_tokens':64}
   try:
    async with s.post('http://127.0.0.1:18300/v1/completions',json=body) as r:
     row.update(status=r.status,router_id=r.headers.get('X-Experiment-Request-ID'));first=None;done=False;usage=None;backend=None
     async for line in r.content:
      if not line.startswith(b'data: '):continue
      val=line[6:].strip()
      if val==b'[DONE]':done=True;continue
      x=json.loads(val);backend=x.get('id',backend)
      if x.get('usage') is not None:
       usage=x['usage']
       if first is None and usage.get('completion_tokens',0)>0:first=time.monotonic_ns()
     row.update(done=done,usage=usage,decode_id=backend,first_token_ns=first,complete_ns=time.monotonic_ns())
   except Exception as e:row.update(error=repr(e),complete_ns=time.monotonic_ns())
   with (out/'requests.jsonl').open('a') as f:f.write(json.dumps(row,separators=(',',':'))+'\n');f.flush();os.fsync(f.fileno())
   if row.get('status')!=200 or not row.get('done') or not row.get('first_token_ns') or not row.get('usage') or row['usage'].get('prompt_tokens')!=512 or row['usage'].get('completion_tokens')!=64:raise RuntimeError(f'request failed index={i}')
 print('complete repeat',rep,flush=True)
asyncio.run(main())
