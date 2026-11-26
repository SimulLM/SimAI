"""Fail-closed per-run process supervisor; formal readiness integration pending."""
import argparse,json,os,pathlib,signal,subprocess,time

def write_status(path,record):
 tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(record,indent=2)+'\n');os.replace(tmp,path)

def group_exists(pgid):
 try:os.killpg(pgid,0);return True
 except ProcessLookupError:return False

def stop_group(proc,grace_s):
 # Signal the whole session even if the launcher has already exited: descendants
 # can still own GPU contexts after their parent dies.
 try:os.killpg(proc.pid,signal.SIGTERM)
 except ProcessLookupError:pass
 deadline=time.monotonic()+grace_s
 while time.monotonic()<deadline:
  proc.poll()
  if not group_exists(proc.pid):return {'leader_exit':proc.returncode,'group_gone':True,'forced':False}
  time.sleep(.1)
 try:os.killpg(proc.pid,signal.SIGKILL)
 except ProcessLookupError:pass
 try:proc.wait(timeout=grace_s)
 except subprocess.TimeoutExpired:pass
 return {'leader_exit':proc.poll(),'group_gone':not group_exists(proc.pid),'forced':True}

def supervise(output,launcher_cmd,ready_path,collector_cmd,gate,*,env=None,startup_timeout_s=400,collector_timeout_s=3600,grace_s=15):
 """Start isolated service group, gate, collect at most one run, then stop group.

 gate is injected for fixture tests; the CLI uses fail_closed_readiness only.
 """
 output=pathlib.Path(output);output.mkdir(parents=True,exist_ok=False);ready_path=pathlib.Path(ready_path)
 if ready_path.exists():raise ValueError('refusing stale service ready file')
 status={'status':'starting','launcher_pid':None,'collector_pid':None,'gate':None,'collector_exit':None,'restart_required':True};write_status(output/'status.json',status)
 service=None;collector=None
 try:
  with (output/'service-supervisor.log').open('w') as log:
   service=subprocess.Popen(launcher_cmd,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);status['launcher_pid']=service.pid;write_status(output/'status.json',status)
   deadline=time.monotonic()+startup_timeout_s
   while not ready_path.is_file():
    if service.poll() is not None:raise RuntimeError('service exited before readiness marker')
    if time.monotonic()>=deadline:raise TimeoutError('service readiness timeout')
    time.sleep(.1)
   if service.poll() is not None:raise RuntimeError('service exited at readiness marker')
   status['gate']=gate();write_status(output/'status.json',status)
   if not status['gate'].get('ready'):status['status']='blocked_idle_gate';return 2
   with (output/'collector-supervisor.log').open('w') as clog:
    collector=subprocess.Popen(collector_cmd,env=env,stdout=clog,stderr=subprocess.STDOUT,start_new_session=True);status['collector_pid']=collector.pid;status['status']='collecting';write_status(output/'status.json',status);deadline=time.monotonic()+collector_timeout_s
    while collector.poll() is None:
     if service.poll() is not None:raise RuntimeError('service exited during collection')
     if time.monotonic()>=deadline:raise TimeoutError('collector deadline exceeded')
     time.sleep(.1)
    status['collector_exit']=collector.returncode
    if collector.returncode!=0:status['status']='collector_failed';return 1
    if service.poll() is not None:raise RuntimeError('service exited at collector completion')
    status['status']='client_collection_complete_reconciliation_required';return 0
 except BaseException as exc:
  status['status']='supervisor_error';status['error']=type(exc).__name__+': '+str(exc)[:300]
  if isinstance(exc,(KeyboardInterrupt,SystemExit)):raise
  return 1
 finally:
  if collector is not None:status['collector_cleanup']=stop_group(collector,grace_s)
  if service is not None:status['service_cleanup']=stop_group(service,grace_s)
  status['service_group_gone']=service is None or status['service_cleanup']['group_gone'];status['finished_monotonic_ns']=time.monotonic_ns();write_status(output/'status.json',status)
  if not status['service_group_gone']:raise RuntimeError('service process group did not terminate; manual cleanup required')

def fail_closed_readiness():
 return {'ready':False,'status':'blocked','reason':'Formal connector idle, fenced admission, worker identity and cleanup gate is not yet integrated; existing metrics-only probe cannot certify readiness.'}

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=pathlib.Path,required=True);p.add_argument('--service-dir',type=pathlib.Path,required=True);p.add_argument('--freeze',type=pathlib.Path,required=True);p.add_argument('--manifest',type=pathlib.Path,required=True);p.add_argument('--run-id',required=True);p.add_argument('--launcher',type=pathlib.Path,required=True);p.add_argument('--python',default='/root/autodl-tmp/venvs/vllm-0.8.5/bin/python');a=p.parse_args()
 # Do not start paid GPU processes until the missing formal readiness gate exists.
 gate=fail_closed_readiness();a.output.mkdir(parents=True,exist_ok=False);write_status(a.output/'status.json',{'status':'blocked_idle_gate','gate':gate,'service_started':False,'restart_required':True});return 2
if __name__=='__main__':raise SystemExit(main())
