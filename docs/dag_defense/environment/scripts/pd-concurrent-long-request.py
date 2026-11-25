import asyncio,json,os,time
from pathlib import Path
import aiohttp
r=Path(os.environ['PD_RUN_DIR']); model='/root/autodl-tmp/models/Llama-2-7b-hf'; rows=[]
prompts=[[1,450+i]+([7483,310,3444,338]*512)[:2046] for i in range(4)]
assert all(len(p)==2048 for p in prompts) and len({tuple(p) for p in prompts})==4
(r/'concurrent-inputs.json').write_text(json.dumps({'token_ids':prompts})+'\n')
async def call(session,port,index):
 body=dict(model=model,prompt=prompts[index],temperature=0,top_p=1,seed=0,ignore_eos=True,stream=False,max_tokens=1 if port==18100 else 2,min_tokens=0 if port==18100 else 2)
 t=time.monotonic_ns()
 try:
  async with session.post(f'http://127.0.0.1:{port}/v1/completions',json=body) as resp:
   data=await resp.json(); row=dict(port=port,index=index,send_ns=t,complete_ns=time.monotonic_ns(),status=resp.status,response=data)
 except Exception as e: row=dict(port=port,index=index,send_ns=t,complete_ns=time.monotonic_ns(),error=repr(e))
 rows.append(row)
 (r/'concurrent-partial.json').write_text(json.dumps(rows,indent=2)+'\n')
 return row
async def main():
 async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=180)) as session:
  pre=await asyncio.gather(*(call(session,18100,i) for i in range(4)))
  assert all(x.get('status')==200 and x['response']['usage']['prompt_tokens']==2048 for x in pre)
  dec=await asyncio.gather(*(call(session,18200,i) for i in range(4)))
  assert all(x.get('status')==200 and x['response']['usage']['prompt_tokens']==2048 and x['response']['usage']['completion_tokens']==2 for x in dec)
asyncio.run(main())
