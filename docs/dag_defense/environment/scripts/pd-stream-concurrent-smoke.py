import asyncio,json,os,time
from pathlib import Path
import aiohttp
r=Path(os.environ['PD_ROUTE_DIR']);model='/root/autodl-tmp/models/Llama-2-7b-hf';rows=[]
async def call(session,index):
 prompt=([1,450+index]+[7483,310,3444,338]*128)[:512];body=dict(model=model,prompt=prompt,temperature=0,top_p=1,seed=0,ignore_eos=True,stream=True,max_tokens=8,min_tokens=8)
 row={'index':index,'send_ns':time.monotonic_ns()};counts=[];done=False
 try:
  async with session.post('http://127.0.0.1:18300/v1/completions',json=body) as response:
   row.update(status=response.status,router_id=response.headers.get('X-Experiment-Request-ID'));raw=[]
   async for line in response.content:
    raw.append(line)
    if not line.startswith(b'data: '):continue
    val=line[6:].strip()
    if val==b'[DONE]':done=True;continue
    data=json.loads(val);row['decode_id']=data.get('id',row.get('decode_id'))
    if data.get('usage') is not None:
     counts.append(data['usage']['completion_tokens']);row['usage']=data['usage']
     if counts[-1]>0 and 'first_token_ns' not in row:row['first_token_ns']=time.monotonic_ns()
   (r/f'concurrent-{index}.sse').write_bytes(b''.join(raw))
  row.update(complete_ns=time.monotonic_ns(),done=done,token_counts=counts)
 except Exception as e:row.update(complete_ns=time.monotonic_ns(),error=repr(e))
 rows.append(row);(r/'concurrent-results.json').write_text(json.dumps(rows,indent=2)+'\n');return row
async def main():
 async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=180)) as session:
  result=await asyncio.gather(*(call(session,i) for i in range(4)))
 assert all(x.get('status')==200 and x.get('done') and x.get('usage',{}).get('prompt_tokens')==512 and x['usage']['completion_tokens']==8 and x['token_counts']==list(range(1,9))+[8] for x in result)
 assert len({x['router_id'] for x in result})==4 and len({x['decode_id'] for x in result})==4
asyncio.run(main())
