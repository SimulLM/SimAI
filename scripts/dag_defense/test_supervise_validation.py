"""Synthetic process tests; no GPU or formal readiness certificate."""
import json,os,pathlib,subprocess,sys,tempfile,time
from supervise_validation import supervise,fail_closed_readiness
with tempfile.TemporaryDirectory() as t:
 root=pathlib.Path(t);py=sys.executable
 service=root/'service.py';service.write_text('import pathlib,sys,time\npathlib.Path(sys.argv[1]).write_text("ready")\nwhile True: time.sleep(1)\n')
 collector=root/'collector.py';collector.write_text('import pathlib,sys,time\npathlib.Path(sys.argv[1]).write_text("started")\ntime.sleep(float(sys.argv[3]))\nsys.exit(int(sys.argv[2]))\n')
 results={}
 for name,gate,exitcode,delay,expected in [('blocked',False,0,0,2),('ok',True,0,0,0),('failed',True,1,0,1),('timeout',True,0,2,1)]:
  ready=root/(name+'.ready');marker=root/(name+'.collector');out=root/name
  rc=supervise(out,[py,str(service),str(ready)],ready,[py,str(collector),str(marker),str(exitcode),str(delay)],lambda:{'ready':gate},startup_timeout_s=5,collector_timeout_s=.5,grace_s=2)
  s=json.loads((out/'status.json').read_text());assert rc==expected and s['service_group_gone'] and s['restart_required'];assert marker.exists()==gate
  assert s['status']=={'blocked':'blocked_idle_gate','ok':'client_collection_complete_reconciliation_required','failed':'collector_failed','timeout':'supervisor_error'}[name]
  results[name]={'exit':rc,'status':s['status'],'service_group_gone':s['service_group_gone']}
 # A launcher exiting after spawning a same-group child must not leave that child running.
 orphan=root/'orphan.py';orphan.write_text('import subprocess,sys,time\nsubprocess.Popen([sys.executable,"-c","import time;time.sleep(60)"])\ntime.sleep(.2)\n')
 out=root/'orphan';rc=supervise(out,[py,str(orphan)],root/'never.ready',[py,'-c','pass'],lambda:{'ready':True},startup_timeout_s=3,grace_s=1);s=json.loads((out/'status.json').read_text());assert rc==1 and s['status']=='supervisor_error' and s['service_group_gone']
 assert fail_closed_readiness()['ready'] is False
 print(json.dumps({'status':'passed','cases':results,'orphan_group_gone':s['service_group_gone'],'scope':'synthetic processes only'},indent=2))
