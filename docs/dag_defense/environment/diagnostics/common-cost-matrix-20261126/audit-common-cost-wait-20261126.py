import pathlib,json,csv,collections,math
p=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/common-cost-matrix-v2-20261126');results=[]
def read(role):
 trace=json.loads(next(role.glob('*/chrome_trace.json')).read_text())['traceEvents']; counts=collections.Counter();out={}
 for e in sorted(trace,key=lambda x:x.get('ts',0)):
  a=e.get('args',{});ids=tuple(sorted(a.get('request_ids',[])));pid=e.get('pid');tok=a.get('num_tokens',[])
  if e.get('ph')!='X' or not ids or a.get('batch_size') is None or pid not in (0,1):continue
  key=(pid,ids,tuple((i,counts[i]) for i in ids),tuple(sorted(tok)));out[key]=e
  if pid==1:
   for i in ids:counts[i]+=1
 return out
for case in sorted(x for x in p.iterdir() if x.is_dir()):
 a=read(case/'dag');b=read(case/'baseline'); timeline=list(csv.DictReader(next((case/'dag').glob('*/timeline.csv')).open())); grouped=collections.defaultdict(list)
 for row in timeline:grouped[row['graph_id']].append(row)
 discrepancies=[];allmatched=[]
 for key in a.keys()&b.keys():
  d=a[key];bid=d['args']['batch_id'];pid=d['pid'];prefix=f'replica{pid}/stage0/batch{bid}/'; graphs=[v for k,v in grouped.items() if k.startswith(prefix)]
  if len(graphs)!=1:discrepancies.append({'key':str(key),'error':'graph mapping','graphs':len(graphs)});continue
  graph=graphs[0];cost=sum(float(x['duration_s']) for x in graph);wait=sum(float(x['resource_wait_s']) for x in graph);sim=float(b[key]['dur'])/1e6;duration=float(d['dur'])/1e6
  row={'key':str(key),'dag_total_s':duration,'dag_sum_task_cost_s':cost,'dag_sum_resource_wait_s':wait,'baseline_batch_total_s':sim,'cost_difference_s':cost-sim,'wait_tasks':[{'task':x['task_id'],'wait_s':float(x['resource_wait_s'])} for x in graph if float(x['resource_wait_s'])>1e-8]}
  allmatched.append(row)
  if abs(cost-sim)>1e-9 or abs((duration-cost)-wait)>1e-9:discrepancies.append(row)
 results.append({'case':case.name,'matched_batches':len(allmatched),'max_abs_cost_difference_s':max((abs(x['cost_difference_s']) for x in allmatched),default=None),'max_resource_wait_s':max((x['dag_sum_resource_wait_s'] for x in allmatched),default=None),'discrepancies':discrepancies,'largest_waits':sorted(allmatched,key=lambda x:x['dag_sum_resource_wait_s'],reverse=True)[:2]})
out={'status':'diagnostic','cases':results,'limits':['One synthetic wave per shape. Matched batches only; many concurrent batch histories differ.','Compares DAG task duration sum against baseline batch total, not separate CPU/GPU components. Assumes task sum is comparable to baseline total for this TP1 graph.','DAG wait is a simulation consequence of configured resource occupancy, not evidence that real transport occupies both GPUs exclusively.','Candidate costs and service-vs-simulator semantics are not frozen.']};(p/'wait-audit.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
