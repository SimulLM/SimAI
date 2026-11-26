"""Close a live stream after first token to test cleanup; diagnostic only."""
import asyncio,json,pathlib,sys,time,aiohttp
out=pathlib.Path(sys.argv[1]);body={'model':'/root/autodl-tmp/models/Llama-2-7b-hf','prompt':[1,412]+[7483]*510,'temperature':0,'top_p':1,'seed':0,'ignore_eos':True,'stream':True,'max_tokens':128,'min_tokens':128}
async def main():
 row={'client_id':'idle-timeout-after-first','send_ns':time.monotonic_ns(),'status':'started'}
 try:
  async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
   async with session.post('http://127.0.0.1:18300/v1/completions',json=body,headers={'X-Experiment-Client-ID':row['client_id']}) as resp:
    row['http_status']=resp.status;row['router_id']=resp.headers.get('X-Experiment-Request-ID')
    async for raw in resp.content:
     if not raw.startswith(b'data: '):continue
     val=raw[6:].strip()
     if val==b'[DONE]':break
     obj=json.loads(val);row['backend_id']=obj.get('id',row.get('backend_id'));usage=obj.get('usage') or {}
     if usage.get('completion_tokens',0)>0:
      row['first_token_ns']=time.monotonic_ns();row['status']='client_cancelled_after_first';resp.close();break
 except Exception as e:row['error']=type(e).__name__+': '+str(e)
 row['client_end_ns']=time.monotonic_ns();out.write_text(json.dumps(row,indent=2)+'\n')
 if row['status']!='client_cancelled_after_first':raise SystemExit(1)
asyncio.run(main())
