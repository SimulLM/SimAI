"""Compare candidate DAG task costs with baseline batch duration where histories match."""
import collections,csv,json,pathlib,sys
root=pathlib.Path(sys.argv[1]);out=pathlib.Path(sys.argv[2]);out.mkdir(exist_ok=False)
def read(role):
 files=list(role.glob('*/chrome_trace.json'))
 if len(files)!=1:raise ValueError('missing or ambiguous trace')
 seq=collections.Counter();result={};duplicates=[]
 for e in sorted(json.loads(files[0].read_text())['traceEvents'],key=lambda x:x.get('ts',0)):
  a=e.get('args',{});ids=tuple(sorted(a.get('request_ids',[])));pid=e.get('pid');tokens=a.get('num_tokens',[])
  if e.get('ph')!='X' or not ids or a.get('batch_size') is None or pid not in (0,1):continue
  key=(pid,ids,tuple((i,seq[i]) for i in ids),tuple(sorted(tokens)))
  if key in result:duplicates.append(str(key))
  result[key]=e
  if pid==1:
   for i in ids:seq[i]+=1
 return result,duplicates
rows=[];summaries=[]
for case in sorted(p for p in root.iterdir() if (p/'request-map.json').exists()):
 a,ad=read(case/'dag');b,bd=read(case/'adapted_baseline');files=list((case/'dag').glob('*/timeline.csv'))
 if len(files)!=1:raise ValueError('missing/ambiguous timeline')
 costs=collections.defaultdict(float); waits=collections.defaultdict(float)
 with files[0].open(newline='') as f:
  for x in csv.DictReader(f):costs[x['graph_id']]+=float(x['duration_s']);waits[x['graph_id']]+=float(x['resource_wait_s'])
 errors=[];common=a.keys()&b.keys();diff=[]
 for key in common:
  event=a[key];prefix=f"replica{event['pid']}/stage0/batch{event['args']['batch_id']}/";matches=[g for g in costs if g.startswith(prefix)]
  if len(matches)!=1:errors.append({'key':str(key),'reason':'graph mapping','count':len(matches)});continue
  graph=matches[0];baseline=float(b[key]['dur'])/1e6;delta=costs[graph]-baseline;diff.append(abs(delta));rows.append({'case':case.name,'key':repr(key),'dag_graph':graph,'dag_task_cost_s':costs[graph],'baseline_batch_s':baseline,'difference_s':delta,'dag_resource_wait_s':waits[graph]})
 summaries.append({'by_replica':{str(pid):{'dag':sum(k[0]==pid for k in a),'baseline':sum(k[0]==pid for k in b),'matched':sum(k[0]==pid for k in common)} for pid in (0,1)},'case':case.name,'dag_batches':len(a),'baseline_batches':len(b),'matched_keys':len(common),'compared':len(diff),'dag_only':len(a.keys()-b.keys()),'baseline_only':len(b.keys()-a.keys()),'duplicate_keys':len(ad)+len(bd),'mapping_errors':errors,'max_abs_difference_s':max(diff) if diff else None,'within_1ns':sum(x<=1e-9 for x in diff),'over_1ns':sum(x>1e-9 for x in diff)})
with (out/'matched.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
result={'status':'matched_batch_diagnostic','cases':summaries,'limitations':['Same request IDs, replica, per-request prior decode count and batch token counts are required to match','Compare summed DAG task costs against baseline batch duration, excluding DAG resource wait; not separate operator validation','Trace timestamps can tie; duplicate history keys are explicitly reported','Unmatched batches cannot establish equal costs','Calibration actual arrivals; no validation or accuracy claim','Adapted baseline is not pristine original']};(out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
