import csv,glob,json,pathlib
base=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/controlled-batches-20261126');result={}
for case,n in [('simultaneous2',2),('simultaneous4',4)]:
 d=base/case; bymode={}
 for mode in ('original','dag'):
  rows=list(csv.DictReader(open(glob.glob(str(d/mode/'2026*/request_metrics.csv'))[0])));assert len(rows)==n
  bymode[mode]=[{'id':int(x['Request Id']),'prefill_end_s':float(x['prefill_completed_at']),'ready_s':float(x['decode_arrived_at']),'reported_comm_s':float(x['pd_p2p_comm_time'])} for x in rows]
 timeline=list(csv.DictReader(open(glob.glob(str(d/'dag/2026*/timeline.csv'))[0])));transfers=[x for x in timeline if x['task_id']=='transfer.0'];assert len(transfers)==n
 taskrows=[]
 for row in transfers:
  taskrows.append({'graph_id':row['graph_id'],'start_s':float(row['start_at_s']),'end_s':float(row['end_at_s']),'duration_s':float(row['duration_s']),'resource_wait_s':float(row['resource_wait_s'])})
 taskrows.sort(key=lambda x:x['start_s'])
 for i,t in enumerate(taskrows):
  assert abs(t['duration_s']-bymode['original'][i]['reported_comm_s'])<1e-9
  assert abs((bymode['dag'][i]['ready_s']-bymode['dag'][i]['prefill_end_s'])-bymode['dag'][i]['reported_comm_s'])<1e-9
  if i: assert abs(t['start_s']-taskrows[i-1]['end_s'])<1e-9
 result[case]={'metrics':bymode,'dag_transfers':taskrows,'note':'DAG request reported comm is ready minus prefill end; it includes queued time; do not add it to transfer task duration or resource wait.'}
pathlib.Path(__file__).with_name('audit.json').write_text(json.dumps(result,indent=2)+'\n')
print('two and four request transfer ownership checks passed')
