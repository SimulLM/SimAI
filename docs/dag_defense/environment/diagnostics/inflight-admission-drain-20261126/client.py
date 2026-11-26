import asyncio,json,pathlib,time,aiohttp
p=pathlib.Path(__file__).parent;router=p/'service/router-events.jsonl';events=[];base='http://127.0.0.1:18300';body={'model':'/root/autodl-tmp/models/Llama-2-7b-hf','prompt':[1,412]+[7483]*2046,'temperature':0,'top_p':1,'seed':0,'ignore_eos':True,'stream':True,'max_tokens':128,'min_tokens':128}
async def main():
 async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=180)) as session:
  async def req():
   async with session.post(base+'/v1/completions',json=body,headers={'X-Experiment-Client-ID':'inflight-fence'}) as resp:
    row={'event':'response','time_ns':time.monotonic_ns(),'status':resp.status,'router_id':resp.headers.get('X-Experiment-Request-ID'),'done':False}
    async for line in resp.content:
     if line.startswith(b'data: '):
      value=line[6:].strip()
      if value==b'[DONE]':row['done']=True
      else:
       x=json.loads(value)
       if x.get('usage') is not None:row['usage']=x['usage']
    row['end_ns']=time.monotonic_ns();events.append(row)
  task=asyncio.create_task(req());deadline=time.monotonic()+10
  while time.monotonic()<deadline:
   if router.exists() and any(x.get('client_request_id')=='inflight-fence' for x in map(json.loads,router.read_text().splitlines())):break
   if task.done():raise RuntimeError('request finished before fence')
   await asyncio.sleep(.001)
  else:raise TimeoutError('router arrival missing')
  async with session.post(base+'/_diagnostic/admission',json={'action':'fence'}) as r:state=await r.json();events.append({'event':'fence','time_ns':time.monotonic_ns(),'status':r.status,'state':state})
  assert state['active']==1 and state['fenced']
  async with session.post(base+'/v1/completions',json=body) as r:events.append({'event':'rejected','time_ns':time.monotonic_ns(),'status':r.status,'body':await r.json()});assert r.status==503
  await task
  async with session.post(base+'/_diagnostic/admission',json={'action':'status'}) as r:state=await r.json();events.append({'event':'drained','time_ns':time.monotonic_ns(),'status':r.status,'state':state})
  assert state['fenced'] and state['active']==0 and state['accepted']==state['finished']==5
 p.joinpath('client-events.json').write_text(json.dumps(events,indent=2)+'\n')
asyncio.run(main())
