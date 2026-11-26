"""Score already reconciled real runs and replay outputs; never grant acceptance."""
import argparse,collections,csv,json,math,pathlib,statistics
FIELDS=('run_id','load','repeat','request_id','input_id','status','actual_s','baseline_s','dag_s','baseline_abs_error_s','dag_abs_error_s','baseline_relative_error','dag_relative_error','comparison','missing_reason')
def finite_positive(value):
 try:x=float(value)
 except (ValueError,TypeError):return None
 return x if math.isfinite(x) and x>0 else None
def score(manifest_path,rule_path,out):
 manifest=json.loads(manifest_path.read_text());rule=json.loads(rule_path.read_text())
 if rule.get('status')!='frozen' or rule.get('comparison')!='absolute_error_s':raise ValueError('explicit frozen scoring rule required')
 eps=rule.get('tie_tolerance_s');
 if not isinstance(eps,(float,int)) or isinstance(eps,bool) or not math.isfinite(eps) or eps<0:raise ValueError('invalid tie tolerance')
 runs=manifest.get('runs',[]);ids=[x['run_id'] for x in runs];keys=[(x['load'],x['repeat']) for x in runs]
 if len(set(ids))!=len(ids) or len(set(keys))!=len(keys):raise ValueError('duplicate run or load/repeat')
 expected={(length,concurrency) for length in (1024,2048) for concurrency in (1,2,4)}
 shapes={(x.get('input_tokens'),x.get('concurrency')) for x in runs}
 if len(runs)!=30 or shapes!=expected or any(x.get('output_tokens')!=128 for x in runs):raise ValueError('invalid planned six-load matrix')
 for shape in expected:
  group=[x for x in runs if (x['input_tokens'],x['concurrency'])==shape]
  if len(group)!=5 or {x['repeat'] for x in group}!={0,1,2,3,4} or len({x['load'] for x in group})!=1:raise ValueError('invalid repeat set or load identity')
 if len({x['load'] for x in runs})!=6:raise ValueError('load label collision')
 result=[];run_summaries=[]
 for run in runs:
  def read(name):
   path=(manifest_path.parent/run[name]).resolve()
   with path.open(newline='',encoding='utf8') as f:return list(csv.DictReader(f))
  actual=read('requests_csv');base=read('baseline_csv');dag=read('dag_csv')
  if len(actual)!=32 or len({r['request_id'] for r in actual})!=32 or any(r['run_id']!=run['run_id'] for r in actual):raise ValueError('invalid actual request identities')
  def index(rows):
   d={}
   for row in rows:
    rid=row['request_id']
    if rid in d:raise ValueError('duplicate prediction request ID')
    d[rid]=row
   if set(d)-{x['request_id'] for x in actual}:raise ValueError('unexpected prediction request ID')
   return d
  bi=index(base);di=index(dag);subset=[]
  for a in actual:
   rid=a['request_id'];b=bi.get(rid);d=di.get(rid);reason=[]
   actual_s=finite_positive(a.get('server_e2e_s')) if a['status']=='success' else None
   if a['status']=='success' and (a.get('actual_input_tokens')!=str(run['input_tokens']) or a.get('actual_output_tokens')!='128'):reason.append('reported token counts do not match run')
   if actual_s is None:reason.append('actual absent, nonpositive, or unsuccessful')
   for label,pred in [('baseline',b),('dag',d)]:
    if pred is None:reason.append(label+' prediction absent')
    elif pred.get('input_id')!=a['input_id']:raise ValueError(label+' input identity mismatch')
   b_s=finite_positive(b.get('predicted_e2e_s')) if b else None;d_s=finite_positive(d.get('predicted_e2e_s')) if d else None
   if b and b_s is None:reason.append('baseline prediction invalid')
   if d and d_s is None:reason.append('dag prediction invalid')
   row={'run_id':run['run_id'],'load':run['load'],'repeat':run['repeat'],'request_id':rid,'input_id':a['input_id'],'status':a['status'],'actual_s':actual_s,'baseline_s':b_s,'dag_s':d_s,'baseline_abs_error_s':None,'dag_abs_error_s':None,'baseline_relative_error':None,'dag_relative_error':None,'comparison':'unscored','missing_reason':'; '.join(reason)}
   if not reason:
    be=abs(b_s-actual_s);de=abs(d_s-actual_s);row.update(baseline_abs_error_s=be,dag_abs_error_s=de,baseline_relative_error=be/actual_s,dag_relative_error=de/actual_s,comparison='improved' if be-de>eps else 'degraded' if de-be>eps else 'tie')
   result.append(row);subset.append(row)
  valid=[x for x in subset if x['comparison']!='unscored'];counts=collections.Counter(x['comparison'] for x in subset)
  run_summaries.append({'run_id':run['run_id'],'load':run['load'],'repeat':run['repeat'],'total':32,'scored':len(valid),'status':'complete' if len(valid)==32 else 'incomplete','comparison_counts':dict(counts),'baseline_mae_s':statistics.mean(x['baseline_abs_error_s'] for x in valid) if valid else None,'dag_mae_s':statistics.mean(x['dag_abs_error_s'] for x in valid) if valid else None,'baseline_mean_relative_error':statistics.mean(x['baseline_relative_error'] for x in valid) if valid else None,'dag_mean_relative_error':statistics.mean(x['dag_relative_error'] for x in valid) if valid else None})
 loads=[]
 for label in sorted({x['load'] for x in runs}):
  group=[x for x in run_summaries if x['load']==label];complete=all(x['status']=='complete' for x in group);counts=collections.Counter()
  for x in group:counts.update(x['comparison_counts'])
  loads.append({'load':label,'repeats':len(group),'complete':complete,'scored':sum(x['scored'] for x in group),'comparison_counts':dict(counts),'baseline_mean_relative_error':statistics.mean(x['baseline_mean_relative_error'] for x in group) if complete else None,'dag_mean_relative_error':statistics.mean(x['dag_mean_relative_error'] for x in group) if complete else None,'baseline_mae_s':statistics.mean(x['baseline_mae_s'] for x in group) if complete else None,'dag_mae_s':statistics.mean(x['dag_mae_s'] for x in group) if complete else None})
 out.mkdir(parents=True,exist_ok=False)
 with (out/'requests.csv').open('w',newline='',encoding='utf8') as f:w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(result)
 summary={'status':'blocked','reason':'scoring alone cannot certify frozen source, same fees, event semantics, input provenance or experimental validity','requests':len(result),'scored':sum(x['scored'] for x in run_summaries),'tie_tolerance_s':eps,'per_repeat':run_summaries,'per_load':loads,'definitions':{'relative_error':'abs(predicted server E2E - measured server E2E) / measured server E2E','improved':'baseline absolute error - DAG absolute error > tie_tolerance_s','aggregation':'equal-weight repeat means only when all five repeats complete'}}
 (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');return summary
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--manifest',type=pathlib.Path,required=True);p.add_argument('--rule',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args();print(json.dumps(score(a.manifest,a.rule,a.output),indent=2))
