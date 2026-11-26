"""Collect one streaming validation run; final freeze and idle verification are required."""
import argparse,asyncio,hashlib,json,os,pathlib,time,traceback
import aiohttp

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def append(p,row):
 with p.open('a',encoding='utf8') as f:f.write(json.dumps(row,separators=(',',':'))+'\n');f.flush();os.fsync(f.fileno())
def preflight(freeze_file,manifest_file,run_id):
 freeze=json.loads(freeze_file.read_text());manifest=json.loads(manifest_file.read_text())
 if freeze.get('status')!='frozen' or freeze.get('validation_manifest_sha256')!=sha(manifest_file):raise ValueError('freeze absent, not frozen, or manifest digest mismatch')
 required=('source','baseline_source','compute_cost','communication_cost','service_configuration','scoring_rule','compatibility_evidence')
 artifacts=freeze.get('artifacts',{})
 for key in required:
  x=artifacts.get(key,{})
  if not x.get('path') or not x.get('sha256') or sha(pathlib.Path(x['path']))!=x['sha256']:raise ValueError('missing or mismatched frozen artifact: '+key)
 matches=[x for x in manifest['runs'] if x['run_id']==run_id]
 if len(matches)!=1:raise ValueError('run_id is not unique in manifest')
 spec=matches[0];p=(manifest_file.parent/spec['path']).resolve()
 if p.parent!=manifest_file.parent.resolve() or sha(p)!=spec['sha256']:raise ValueError('input file path or digest mismatch')
 rows=[json.loads(x) for x in p.read_text().splitlines()]
 if len(rows)!=32 or spec['requests']!=32:raise ValueError('expected 32 inputs')
 for i,r in enumerate(rows):
  raw=(json.dumps(r['input_ids'],separators=(',',':'),ensure_ascii=True)+'\n').encode()
  if hashlib.sha256(raw).hexdigest()!=r['input_sha256'] or len(r['input_ids'])!=spec['input_tokens'] or r['wave']!=i//spec['concurrency']:raise ValueError('input row integrity mismatch')
 return freeze,manifest,spec,rows
async def run_case(spec,rows,output,url,model,timeout_s):
 output.mkdir(parents=True,exist_ok=False);origin=time.monotonic_ns();(output/'run-spec.json').write_text(json.dumps({'spec':spec,'clock_id':'CLOCK_MONOTONIC','origin_ns':origin,'url':url,'model':model,'timeout_s':timeout_s,'sampling':{'temperature':0,'top_p':1,'seed':0,'ignore_eos':True,'min_tokens':128,'max_tokens':128}},indent=2)+'\n');path=output/'client-events.jsonl'
 async def one(session,r,scheduled):
  row={'run_id':r['run_id'],'request_id':r['request_id'],'input_id':r['input_id'],'input_sha256':r['input_sha256'],'wave':r['wave'],'scheduled_arrival_ns':scheduled,'client_send_ns':time.monotonic_ns(),'status':'failed'}
  try:
   body={'model':model,'prompt':r['input_ids'],'temperature':0,'top_p':1,'seed':0,'ignore_eos':True,'stream':True,'max_tokens':128,'min_tokens':128}
   async with session.post(url,json=body) as resp:
    row['http_status']=resp.status;row['router_id']=resp.headers.get('X-Experiment-Request-ID');row['client_headers_ns']=time.monotonic_ns();done=False;usage=None;backend=None;first=None
    if resp.status!=200:row['error']='HTTP '+str(resp.status)+' '+(await resp.text())[:512]
    else:
     async for line in resp.content:
      stamp=time.monotonic_ns()
      if not line.startswith(b'data: '):continue
      value=line[6:].strip()
      if value==b'[DONE]':done=True;continue
      obj=json.loads(value);backend=obj.get('id',backend)
      if obj.get('usage') is not None:
       usage=obj['usage']
       if first is None and usage.get('completion_tokens',0)>0:first=stamp
     row.update(done=done,usage=usage,backend_request_id=backend,client_first_token_ns=first)
     if done and first is not None and row['router_id'] and usage and usage.get('prompt_tokens')==spec['input_tokens'] and usage.get('completion_tokens')==128:row['status']='success'
     else:row['error']='incomplete stream, ID, first token, or token count'
  except asyncio.TimeoutError:row.update(status='timeout',error='client deadline exceeded')
  except Exception as exc:row.update(status='failed',error=type(exc).__name__+': '+str(exc)[:512])
  finally:row['client_complete_ns']=time.monotonic_ns();append(path,row)
  return row
 async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout_s)) as session:
  for w in range((len(rows)+spec['concurrency']-1)//spec['concurrency']):
   batch=[r for r in rows if r['wave']==w];scheduled=time.monotonic_ns();append(output/'wave-events.jsonl',{'wave':w,'event':'scheduled','timestamp_ns':scheduled,'request_count':len(batch)});result=await asyncio.gather(*(one(session,r,scheduled) for r in batch));append(output/'wave-events.jsonl',{'wave':w,'event':'complete','timestamp_ns':time.monotonic_ns(),'status_counts':{s:sum(x['status']==s for x in result) for s in ('success','failed','timeout')}})
   if any(x['status']!='success' for x in result):
    for r in rows:
     if r['wave']>w:append(path,{'run_id':r['run_id'],'request_id':r['request_id'],'input_id':r['input_id'],'input_sha256':r['input_sha256'],'wave':r['wave'],'status':'not_submitted','error':'earlier wave failed or timed out; server idle is unverified'})
    break
 (output/'client-complete.json').write_text(json.dumps({'finished_ns':time.monotonic_ns(),'requested':len(rows),'note':'client collection ended; server events, idle and validity must be verified separately'},indent=2)+'\n')
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--freeze',type=pathlib.Path,required=True);ap.add_argument('--manifest',type=pathlib.Path,required=True);ap.add_argument('--run-id',required=True);ap.add_argument('--output',type=pathlib.Path,required=True);ap.add_argument('--url',default='http://127.0.0.1:18300/v1/completions');ap.add_argument('--model',default='/root/autodl-tmp/models/Llama-2-7b-hf');ap.add_argument('--timeout',type=float,default=180);args=ap.parse_args();freeze,manifest,spec,rows=preflight(args.freeze,args.manifest,args.run_id);asyncio.run(run_case(spec,rows,args.output,args.url,args.model,args.timeout))
