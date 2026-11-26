"""Verify incomplete or zero gauges can never serve as a readiness success."""
import json,pathlib,sys,tempfile,unittest.mock
import probe_pd_idle as probe
with tempfile.TemporaryDirectory() as temp:
 root=pathlib.Path(temp);router=root/'router.jsonl';router.write_text(json.dumps({'request_id':'r','event':'server_arrival'})+'\n'+json.dumps({'request_id':'r','event':'server_complete'})+'\n')
 for label,values,want in [('zero',{k:0.0 for k in probe.NAMES},2),('missing',{k:(None if k==probe.NAMES[2] else 0.0) for k in probe.NAMES},2),('busy',{k:(1.0 if k==probe.NAMES[0] else 0.0) for k in probe.NAMES},1)]:
  with unittest.mock.patch.object(sys,'argv',['probe','--router-events',str(router),'--output',str(root/label),'--samples','2','--interval','0.01']),unittest.mock.patch.object(probe,'fetch',return_value=values):
   assert probe.main()==want
  s=json.loads((root/label/'summary.json').read_text());assert s['status'] in ('gauges_zero_connector_unverified','incomplete','observed_busy_or_error')
 print('PASS: zero or missing gauges remain unverified; busy state rejected')
