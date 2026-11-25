"""Calibration request collector; does not tune fees."""
import argparse,asyncio,json,os,time,hashlib
from pathlib import Path
import aiohttp
p=argparse.ArgumentParser();p.add_argument('--run-dir',type=Path,required=True);p.add_argument('--repeats',type=int,default=3);a=p.parse_args();r=a.run_dir;r.mkdir(parents=True,exist_ok=False)
model='/root/autodl-tmp/models/Llama-2-7b-hf'; rows=[];events=[]
def prompt(rep,mode,index):return ([1,450+rep*10+index]+[7483,310,3444,338]*130)[:512]
async def call(session,rep,mode,index):
 ids=prompt(rep,mode,index);body=dict(model=model,prompt=ids,temperature=0,top_p=1,seed=0,ignore_eos=True,stream=True,max_tokens=64,min_tokens=64);start=time.monotonic_ns();row=dict(repeat=rep,mode=mode,index=index,input_sha256=hashlib.sha256(bytes(str(ids),'utf8')).hexdigest(),send_ns=start)
 try:
  async with session.post('http://127.0.0.1:18300/v1/completions',json=body) as resp:
   row.update(status=resp.status,router_id=resp.headers.get('X-Experiment-Request-ID'));counts=[];done=False;first=None;decode_id=None
   async for line in resp.content:
    if not line.startswith(b'data: '):continue
    val=line[6:].strip()
    if val==b'[DONE]':done=True;continue
    obj=json.loads(val);decode_id=obj.get('id',decode_id)
    if obj.get('usage') is not None:
     counts.append(obj['usage'].get('completion_tokens',0))
     if first is None and counts[-1]>0:first=time.monotonic_ns()
     row['usage']=obj['usage']
   row.update(done=done,decode_id=decode_id,token_counts=counts,first_token_ns=first,complete_ns=time.monotonic_ns())
 except Exception as e:row.update(error=repr(e),complete_ns=time.monotonic_ns())
 rows.append(row)
async def main():
 async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=600)) as session:
  for rep in range(a.repeats):
   for mode in ('serial','concurrent2'):
    for wave in range(16):
     idxs=[wave] if mode=='serial' else [wave*2,wave*2+1]
     await asyncio.gather(*(call(session,rep,mode,i) for i in idxs))
    print('finished',rep,mode,flush=True)
 (r/'requests.json').write_text(json.dumps(rows,indent=2)+'\n')
 assert len(rows)==3*16*3 and all(x.get('status')==200 and x.get('done') and x.get('usage',{}).get('prompt_tokens')==512 and x['usage']['completion_tokens']==64 and x['token_counts'][-1]==64 for x in rows)
 (r/'result.json').write_text(json.dumps(dict(status='passed',requests=len(rows),matrix='3 repeats x serial/concurrent2 x 32 requests, input 512/output 64',fee_fitting='not performed',rows=rows),indent=2)+'\n')
asyncio.run(main())
