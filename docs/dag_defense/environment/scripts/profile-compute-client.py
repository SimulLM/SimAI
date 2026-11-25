"""Generate independent synthetic token inputs for diagnostic CUDA-event costs."""
import argparse,asyncio,json,time,os
from pathlib import Path
import aiohttp
p=argparse.ArgumentParser();p.add_argument('--run-dir',type=Path,required=True);p.add_argument('--warmups',type=int,default=10);p.add_argument('--samples',type=int,default=30);p.add_argument('--lengths',type=int,nargs='+',default=[512,1024,2048]);p.add_argument('--batches',type=int,nargs='+',default=[1,2,4]);a=p.parse_args();r=a.run_dir
spec={'lengths':a.lengths,'batches':a.batches,'warmup_waves':a.warmups,'measured_waves':a.samples,'prompt_rule':'[1, 450 + index] + repeat([7483,310,3444,338]) to requested length','model':'/root/autodl-tmp/models/Llama-2-7b-hf','temperature':0,'seed':0,'ignore_eos':True,'min_tokens':2,'max_tokens':2,'nature':'independent profiling inputs; not validation'}
(r/'client-spec.json').write_text(json.dumps(spec,indent=2)+'\n')
async def send(session,n,b,wave,index):
 prompt=([1,450+index]+[7483,310,3444,338]*((n+3)//4))[:n]
 body=dict(model=spec['model'],prompt=prompt,temperature=0,top_p=1,seed=0,ignore_eos=True,stream=False,max_tokens=2,min_tokens=2)
 start=time.monotonic_ns();row=dict(length=n,batch=b,wave=wave,warmup=wave<a.warmups,index=index,start_ns=start)
 try:
  async with session.post('http://127.0.0.1:18300/v1/completions',json=body) as response:
   data=await response.json();row.update(status=response.status,request_id=data.get('id'),usage=data.get('usage'),finish_reason=(data.get('choices') or [{}])[0].get('finish_reason'))
   if response.status!=200 or data.get('usage',{}).get('prompt_tokens')!=n or data.get('usage',{}).get('completion_tokens')!=2:row['error']=str(data)[:500]
 except Exception as e:row['error']=repr(e)
 row['end_ns']=time.monotonic_ns()
 with (r/'client-requests.jsonl').open('a') as f:f.write(json.dumps(row,separators=(',',':'))+'\n')
 return row
async def main():
 count=0
 async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=180)) as session:
  for n in a.lengths:
   for b in a.batches:
    for wave in range(a.warmups+a.samples):
     rows=await asyncio.gather(*(send(session,n,b,wave,i) for i in range(b)));count+=len(rows)
     if any('error' in x for x in rows):raise RuntimeError(f'failed wave n={n} b={b} wave={wave}')
    print(f'completed n={n} batch={b} waves={a.warmups+a.samples} requests={count}',flush=True)
asyncio.run(main())
