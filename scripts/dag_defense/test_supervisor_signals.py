"""Send SIGTERM/SIGINT to a supervisor and verify its child groups exit."""
import json,os,pathlib,signal,subprocess,sys,tempfile,time
with tempfile.TemporaryDirectory() as td:
 p=pathlib.Path(td);py=sys.executable;here=pathlib.Path(__file__).parent
 (p/'service.py').write_text('import pathlib,sys,time\npathlib.Path(sys.argv[1]).write_text("ready")\nwhile True:time.sleep(1)\n')
 (p/'collector.py').write_text('import pathlib,sys,time\npathlib.Path(sys.argv[1]).write_text("started")\nwhile True:time.sleep(1)\n')
 (p/'parent.py').write_text('import pathlib,sys\nsys.path.insert(0,sys.argv[1])\nfrom supervise_validation import supervise\np=pathlib.Path(sys.argv[2]);supervise(p/"out",[sys.executable,str(p/"service.py"),str(p/"ready")],p/"ready",[sys.executable,str(p/"collector.py"),str(p/"collector.started")],lambda:{"ready":True},startup_timeout_s=5,grace_s=3)\n')
 results={}
 for sig in (signal.SIGTERM,signal.SIGINT):
  q=p/str(sig);q.mkdir();
  for name in ('service.py','collector.py','parent.py'):(q/name).write_bytes((p/name).read_bytes())
  process=subprocess.Popen([py,str(q/'parent.py'),str(here),str(q)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  deadline=time.monotonic()+10
  while not (q/'collector.started').exists() and process.poll() is None and time.monotonic()<deadline:time.sleep(.05)
  assert (q/'collector.started').exists();os.kill(process.pid,sig);rc=process.wait(timeout=12);status=json.loads((q/'out/status.json').read_text())
  assert rc!=0 and status['status']=='interrupted' and status['service_group_gone'] and status['collector_cleanup']['group_gone'] and status['restart_required']
  results[sig.name]={'returncode':rc,'status':status['status'],'service_group_gone':True,'collector_group_gone':True}
 print(json.dumps({'status':'passed','signals':results,'scope':'synthetic processes, no GPU'},indent=2))
