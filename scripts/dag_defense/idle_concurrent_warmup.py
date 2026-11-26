"""Four distinct 512/8 streaming requests for connector-idle diagnostic."""
import asyncio,json,pathlib,sys,time,aiohttp
out=pathlib.Path(sys.argv[1]);model='/root/autodl-tmp/models/Llama-2-7b-hf'
async def main():
 async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as session:
  async def one(i):
   body={'model':model,'prompt':[1,400+i]+[7483]*510,'temperature':0,'top_p':1,'seed':0,'ignore_eos':True,'stream':True,'max_tokens':8,'min_tokens':8}
   row={'index':i,'send_ns':time.monotonic_ns(),'done':False}
   async with session.post('http://127.0.0.1:18300/v1/completions',json=body,headers={'X-Experiment-Client-ID':f'idle-concurrent-{i}'}) as r:
    row['status']=r.status;row['router_id']=r.headers.get('X-Experiment-Request-ID')
    async for raw in r.content:
     if not raw.startswith(b'data: '):continue
     val=raw[6:].strip()
     if val==b'[DONE]':row['done']=True;continue
     x=json.loads(val);row['backend_id']=x.get('id',row.get('backend_id'));row['usage']=x.get('usage') or row.get('usage')
   row['complete_ns']=time.monotonic_ns();return row
  rows=await asyncio.gather(*(one(i) for i in range(4)))
 out.write_text(json.dumps(rows,indent=2)+'\n')
 assert all(x['status']==200 and x['done'] and x['router_id'] and x['usage']['prompt_tokens']==512 and x['usage']['completion_tokens']==8 for x in rows)
asyncio.run(main())
