import asyncio,json,os,time
from pathlib import Path
import aiohttp
r=Path(os.environ['PD_ROUTE_DIR']); model='/root/autodl-tmp/models/Llama-2-7b-hf';prompt=([1]+[450,7483,310,3444,338]*103)[:512]
body=dict(model=model,prompt=prompt,temperature=0,top_p=1,seed=0,ignore_eos=True,stream=True,max_tokens=8,min_tokens=8)
async def main():
 events=[];usage=None;done=False;first=False;decode_id=None
 async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=180)) as session:
  events.append(dict(event='client_send',timestamp_ns=time.monotonic_ns()))
  async with session.post('http://127.0.0.1:18300/v1/completions',json=body) as response:
   rid=response.headers.get('X-Experiment-Request-ID');events.append(dict(event='client_headers',timestamp_ns=time.monotonic_ns(),status=response.status,router_id=rid));assert response.status==200 and rid
   with (r/'client-response.sse').open('wb') as raw:
    async for line in response.content:
     raw.write(line)
     if not line.startswith(b'data: '):continue
     val=line[6:].strip()
     if val==b'[DONE]':done=True;continue
     obj=json.loads(val);decode_id=obj.get('id',decode_id);choices=obj.get('choices') or []
     if obj.get('usage') and obj['usage'].get('completion_tokens',0)>0 and not first:events.append(dict(event='client_first_token',timestamp_ns=time.monotonic_ns()));first=True
     if obj.get('usage') is not None:usage=obj['usage']
  events.append(dict(event='client_complete',timestamp_ns=time.monotonic_ns(),done=done,usage=usage,decode_id=decode_id))
  (r/'client-events.json').write_text(json.dumps(events,indent=2)+'\n')
  assert first and done and usage and usage['prompt_tokens']==512 and usage['completion_tokens']==8
  bad=dict(body,model='nonexistent-model')
  async with session.post('http://127.0.0.1:18300/v1/completions',json=bad) as response:
   payload=await response.text(); (r/'failure-response.json').write_text(json.dumps(dict(status=response.status,router_id=response.headers.get('X-Experiment-Request-ID'),body=payload))+'\n');assert response.status>=400
asyncio.run(main())
