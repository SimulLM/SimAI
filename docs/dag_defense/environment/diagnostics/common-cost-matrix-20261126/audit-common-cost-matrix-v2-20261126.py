import csv,glob,hashlib,json,math,pathlib,collections
p=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/common-cost-matrix-v2-20261126')
def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
def events(folder):
 f=next(folder.glob('*/chrome_trace.json'));data=json.loads(f.read_text())['traceEvents']; seen=collections.Counter();out={};dups=[]
 for ev in sorted(data,key=lambda e:e.get('ts',0)):
  arg=ev.get('args',{});ids=tuple(sorted(arg.get('request_ids',[])));batch=arg.get('batch_size');toks=arg.get('num_tokens',[]);pid=ev.get('pid')
  if ev.get('ph')!='X' or not ids or batch is None or pid not in (0,1):continue
  key=(pid,ids,tuple((rid,seen[rid]) for rid in ids),tuple(sorted(toks)))
  if key in out:dups.append(str(key))
  out[key]=float(ev['dur'])/1e6
  if pid==1:
   for rid in ids:seen[rid]+=1
 return out,dups
def hashes(role):return {x.name:sha(x) for x in (role/'cache').glob('*_training_predictions.csv')}
def metrics(role):return list(csv.DictReader(next(role.glob('*/request_metrics.csv')).open()))
results=[]
for case in sorted(x for x in p.iterdir() if x.is_dir()):
 a,ad=events(case/'dag');b,bd=events(case/'baseline');common=a.keys() & b.keys();diffs=[abs(a[k]-b[k]) for k in common];ma=metrics(case/'dag');mb=metrics(case/'baseline');ha=hashes(case/'dag');hb=hashes(case/'baseline')
 results.append({'case':case.name,'dag_events':len(a),'baseline_events':len(b),'matched_events':len(common),'dag_only':len(a.keys()-b.keys()),'baseline_only':len(b.keys()-a.keys()),'duplicate_keys':len(ad)+len(bd),'max_matched_batch_total_difference_s':max(diffs) if diffs else None,'all_matched_within_1ns':bool(diffs) and max(diffs)<1e-9,'training_predictions_equal':bool(ha) and ha==hb,'training_prediction_files':len(ha),'dag_requests':len(ma),'baseline_requests':len(mb),'dag_pd_times_s':[float(x['pd_p2p_comm_time']) for x in ma],'baseline_pd_times_s':[float(x['pd_p2p_comm_time']) for x in mb],'dag_exit':int((case/'dag/exit-code').read_text()),'baseline_exit':int((case/'baseline/exit-code').read_text())})
out={'status':'synthetic_matched_batch_audit_only','cases':results,'limits':['Candidate profile, not frozen or calibrated; synthetic simultaneous arrivals, not real service data','Matching includes request IDs and their per-request previous decode iteration count, replica ID and number of tokens. GPU/CPU and PD fields must still be separately accounted','batch trace duration compares total execution only and does not prove matching of each component or mixed-length shapes','two schedulers may form different batches, so unmatched batches are not cost failures','adapter changes predictor compared with untouched original; original baseline separately preserved']};(p/'common-cost-audit.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
