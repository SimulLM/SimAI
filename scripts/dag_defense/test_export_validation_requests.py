"""Verify failure rows and clock-boundary arithmetic using synthetic records."""
import csv,json,pathlib,tempfile
from export_validation_requests import export

def test_export_preserves_missing_and_clocks():
 with tempfile.TemporaryDirectory() as td:
  root=pathlib.Path(td);origin=1000000000;spec=root/'spec.json';spec.write_text(json.dumps({'origin_ns':origin,'clock_id':'CLOCK_MONOTONIC'}));rows=[]
  for i in range(32):
   row={'run_id':'r','request_id':str(i),'input_id':str(i),'status':'success','error':'','scheduled_arrival_ns':origin,'client_send_ns':origin+100,'server_arrival_ns':origin+200,'client_first_token_ns':origin+500,'server_complete_ns':origin+900,'client_complete_ns':origin+1000,'usage':{'prompt_tokens':512,'completion_tokens':3}}
   if i==1:row.update(status='timeout',server_complete_ns=None,client_first_token_ns=None,usage=None)
   if i==2:row={'run_id':'r','request_id':'2','input_id':'2','status':'not_submitted','error':'prior timeout'}
   rows.append(row)
  src=root/'in.jsonl';src.write_text(''.join(json.dumps(x)+'\n' for x in rows));result=export(src,spec,root/'out');assert result['rows']==32 and result['status_counts']=={'not_submitted':1,'success':30,'timeout':1}
  with (root/'out/requests.csv').open() as f:out=list(csv.DictReader(f))
  assert abs(float(out[0]['server_e2e_s'])-7e-7)<1e-15 and abs(float(out[0]['client_tpot_s'])-2.5e-7)<1e-15
  assert out[1]['server_complete_s']=='' and out[2]['client_send_s']==''
  missing=json.loads((root/'out/missing-fields.json').read_text())['missing'];assert any(x['request_id']=='1' and x['field']=='server_complete_s' for x in missing)
  rows[0]['server_complete_ns']=origin+1;src.write_text(''.join(json.dumps(x)+'\n' for x in rows))
  try:export(src,spec,root/'bad')
  except AssertionError:pass
  else:raise AssertionError('negative server interval accepted')
