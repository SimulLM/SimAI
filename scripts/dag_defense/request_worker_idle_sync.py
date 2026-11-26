"""Request process-local CUDA synchronization outside E2E measurement."""
import argparse,json,os,pathlib,re,time,uuid
p=argparse.ArgumentParser();p.add_argument('--observer',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);p.add_argument('--timeout',type=float,default=30);a=p.parse_args()
assert a.observer.is_dir() and not (a.observer/'sync-request.json').exists() and not a.output.exists() and a.timeout>0
nonce=uuid.uuid4().hex;request=a.observer/'sync-request.json';temp=a.observer/f'.request-{nonce}.tmp';temp.write_text(json.dumps({'nonce':nonce})+'\n');os.replace(temp,request);deadline=time.monotonic()+a.timeout;found=[]
while time.monotonic()<deadline:
 files=list(a.observer.glob(f'sync-{nonce}-*.json'))
 if len(files)>=2:
  found=[json.loads(f.read_text()) for f in files];break
 time.sleep(.2)
status='completed' if len(found)==2 and {x.get('role') for x in found}=={'producer','consumer'} and all(x.get('status')=='completed' and x.get('nonce')==nonce and x.get('end_ns',0)>=x.get('start_ns',1) for x in found) else 'incomplete'
result={'status':status,'nonce':nonce,'clock_id':'CLOCK_MONOTONIC','workers':found,'limitations':['Synchronization only covers each responding worker process CUDA context and previously submitted work','Host queue, in-flight request, pipe and live PID ownership must be independently verified before and after','No new requests may be issued during synchronization and observation','Observer thread itself changes process behavior; no formal readiness certification']};a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));raise SystemExit(0 if status=='completed' else 1)
