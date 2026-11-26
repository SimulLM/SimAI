import json,os,pathlib,signal,subprocess,sys,time
p=pathlib.Path(__file__).parent;log=(p/'parent.log').open('w');proc=subprocess.Popen([sys.executable,str(p/'parent.py')],stdout=log,stderr=subprocess.STDOUT);deadline=time.monotonic()+400
while time.monotonic()<deadline:
 status=p/'supervisor/status.json'
 if status.exists() and json.loads(status.read_text()).get('status')=='collecting':break
 if proc.poll() is not None:raise RuntimeError('supervisor stopped before collecting')
 time.sleep(.2)
else:proc.terminate();raise TimeoutError('startup')
# This is a test signal sent only to the diagnostic supervisor PID.
os.kill(proc.pid,signal.SIGTERM);code=proc.wait(timeout=60);log.close();s=json.loads(status.read_text());assert code!=0 and s['status']=='interrupted' and s['service_group_gone'] and s['collector_group_gone']
r=subprocess.run(['nvidia-smi','--query-gpu=index,memory.used','--format=csv,noheader,nounits'],capture_output=True,text=True,check=True);(p/'gpu-after.csv').write_text(r.stdout);mem=[int(x.split(',')[1]) for x in r.stdout.splitlines()];assert mem==[0,0],mem
(p/'result.json').write_text(json.dumps({'parent_exit':code,'status':s['status'],'service_group_gone':s['service_group_gone'],'collector_group_gone':s['collector_group_gone'],'gpu_memory_mib':mem},indent=2)+'\n');print('PASS real service SIGTERM cleanup')
