import asyncio,aiohttp,json,pathlib,time,hashlib,random,os,sys
out=pathlib.Path(sys.argv[1]);out.mkdir(exist_ok=False);model='/root/autodl-tmp/models/Llama-2-7b-hf'
async def main():
 async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=180)) as s:
  for i in range(-4,16):
   rng=random.Random(20261326+i);ids=[1]+[rng.randrange(4,31999) for _ in range(511)];row={'index':i,'warmup':i<0,'input_ids':ids,'input_sha256':hashlib.sha256(json.dumps(ids,separators=(',',':')).encode()).hexdigest(),'send_ns':time.monotonic_ns(),'tokens':[]};body={'model':model,'prompt':ids,'temperature':0,'top_p':1,'seed':0,'ignore_eos':True,'stream':True,'max_tokens':64,'min_tokens':64}
   try:
    async with s.post('http://127.0.0.1:18300/v1/completions',json=body) as r:
     row.update(status=r.status,router_id=r.headers.get('X-Experiment-Request-ID'));done=False;usage=None;backend=None
     async for line in r.content:
      stamp=time.monotonic_ns()
      if not line.startswith(b'data: '):continue
      val=line[6:].strip()
      if val==b'[DONE]':done=True;continue
      x=json.loads(val);backend=x.get('id',backend)
      if x.get('usage') is not None:
       usage=x['usage'];count=usage.get('completion_tokens',0)
       if count>0 and (not row['tokens'] or row['tokens'][-1]['count']!=count):row['tokens'].append({'count':count,'received_ns':stamp})
     row.update(done=done,usage=usage,decode_id=backend,complete_ns=time.monotonic_ns())
   except Exception as e:row.update(error=repr(e),complete_ns=time.monotonic_ns())
   with (out/'requests.jsonl').open('a') as f:f.write(json.dumps(row,separators=(',',':'))+'\n');f.flush();os.fsync(f.fileno())
   if row.get('status')!=200 or not row.get('done') or not row.get('usage') or row['usage'].get('prompt_tokens')!=512 or row['usage'].get('completion_tokens')!=64 or [x['count'] for x in row['tokens']]!=list(range(1,65)):raise RuntimeError(f'failed request or token sequence index={i}')
asyncio.run(main())
