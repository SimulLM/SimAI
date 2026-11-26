import argparse,asyncio,json,time,hashlib
from pathlib import Path
import aiohttp
p=argparse.ArgumentParser(); p.add_argument('--run-dir',required=True); p.add_argument('--warmups',type=int,default=10); p.add_argument('--samples',type=int,default=30); p.add_argument('--lengths',type=int,nargs='+',default=[512,1024,2048]); p.add_argument('--batches',type=int,nargs='+',default=[1,2,4]); p.add_argument('--timeout',type=int,default=45); a=p.parse_args(); out=Path(a.run_dir); out.mkdir(parents=True,exist_ok=False)
lengths=a.lengths; batches=a.batches; model='/root/autodl-tmp/models/Llama-2-7b-hf'
spec={'lengths':lengths,'batches':batches,'warmup_waves':a.warmups,'measured_waves':a.samples,'model':model,'max_tokens':2,'min_tokens':2,'nature':'independent real PD outer CUDA profile'}; (out/'client-spec.json').write_text(json.dumps(spec,indent=2)+'\n')
async def one(s,n,b,w,i):
 ids=([1,450+i]+[7483,310,3444,338]*((n+3)//4))[:n]; row={'length':n,'batch':b,'wave':w,'index':i,'warmup':w<a.warmups,'send_ns':time.monotonic_ns(),'input_sha256':hashlib.sha256(bytes(str(ids),'utf8')).hexdigest()}
 try:
  async with s.post('http://127.0.0.1:18300/v1/completions',json={'model':model,'prompt':ids,'temperature':0,'top_p':1,'seed':0,'ignore_eos':True,'stream':False,'max_tokens':2,'min_tokens':2}) as r:
   body=await r.read(); data=json.loads(body); row.update(status=r.status,bytes=len(body),usage=data.get('usage'),finish_reason=(data.get('choices') or [{}])[0].get('finish_reason'),end_ns=time.monotonic_ns())
 except Exception as e: row.update(status=0,error=repr(e),end_ns=time.monotonic_ns())
 with (out/'requests.jsonl').open('a') as f: f.write(json.dumps(row,separators=(',',':'))+'\n')
 return row
async def main():
 async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=a.timeout)) as s:
  for n in lengths:
   for b in batches:
    for w in range(a.warmups+a.samples):
     rows=await asyncio.gather(*(one(s,n,b,w,i) for i in range(b)))
     if any(r.get('status')!=200 or r.get('usage',{}).get('prompt_tokens')!=n or r.get('usage',{}).get('completion_tokens')!=2 for r in rows): raise RuntimeError(f'failed n={n} b={b} wave={w}')
    print('done',n,b,flush=True)
asyncio.run(main())
