"""Exercise three-way scoring and incomplete-run handling with synthetic data."""
import csv,json,pathlib,tempfile
from score_validation_replays import score

def write_csv(path,fields,rows):
 with path.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def test_scoring_blocks_missing_and_preserves_regressions():
 with tempfile.TemporaryDirectory() as td:
  root=pathlib.Path(td);runs=[]
  for load in range(6):
   for rep in range(5):
    rid=f'r{load}{rep}';a=[];b=[];d=[]
    for i in range(32):
     key=f'{rid}-{i}';a.append({'run_id':rid,'request_id':key,'input_id':key,'status':'success','server_e2e_s':'1','actual_input_tokens':str((1024,2048)[load//3]),'actual_output_tokens':'128'});b.append({'request_id':key,'input_id':key,'predicted_e2e_s':'1.2'});d.append({'request_id':key,'input_id':key,'predicted_e2e_s':'1.1' if i else '1.4'})
    if load==0 and rep==0:a[1]['status']='timeout';a[1]['server_e2e_s']='';d=d[:-1]
    for name,fields,rows in [('a',['run_id','request_id','input_id','status','server_e2e_s','actual_input_tokens','actual_output_tokens'],a),('b',['request_id','input_id','predicted_e2e_s'],b),('d',['request_id','input_id','predicted_e2e_s'],d)]:write_csv(root/f'{rid}-{name}.csv',fields,rows)
    runs.append({'run_id':rid,'load':str(load),'repeat':rep,'input_tokens':(1024,2048)[load//3],'output_tokens':128,'concurrency':(1,2,4)[load%3],'requests_csv':f'{rid}-a.csv','baseline_csv':f'{rid}-b.csv','dag_csv':f'{rid}-d.csv'})
  manifest=root/'manifest.json';manifest.write_text(json.dumps({'runs':runs}));rule=root/'rule.json';rule.write_text(json.dumps({'status':'frozen','comparison':'absolute_error_s','tie_tolerance_s':0.0}));summary=score(manifest,rule,root/'out')
  assert summary['status']=='blocked' and summary['requests']==960 and summary['scored']==958
  first=next(x for x in summary['per_repeat'] if x['run_id']=='r00');assert first['status']=='incomplete' and first['comparison_counts']['unscored']==2 and first['comparison_counts']['degraded']==1
  load=next(x for x in summary['per_load'] if x['load']=='0');assert not load['complete'] and load['dag_mean_relative_error'] is None
  good=next(x for x in summary['per_load'] if x['load']=='1');assert good['complete'] and good['scored']==160 and good['comparison_counts']['degraded']==5
  bad=json.loads(manifest.read_text());bad['runs'][0]['output_tokens']=64;manifest.write_text(json.dumps(bad))
  try:score(manifest,rule,root/'wrong-matrix')
  except ValueError:pass
  else:raise AssertionError('wrong matrix accepted')
  manifest.write_text(json.dumps({'runs':runs}))
  rule.write_text(json.dumps({'status':'draft','comparison':'absolute_error_s','tie_tolerance_s':0.0}))
  try:score(manifest,rule,root/'unfrozen')
  except ValueError:pass
  else:raise AssertionError('unfrozen rule accepted')
