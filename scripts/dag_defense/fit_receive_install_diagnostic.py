"""Fit inclusive, synchronized serial receiver intervals on independent samples."""
import csv,hashlib,json,math,pathlib,statistics,sys
source=pathlib.Path(sys.argv[1]);out=pathlib.Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=False)
with source.open() as f:rows=list(csv.DictReader(f))
rows=[{'length':int(r['length']),'wave':int(r['wave']),'y_ms':float(r['receive_to_install_sync_ms'])} for r in rows if r['warmup']=='False']
assert len(rows)==90 and all(sum(x['length']==n for x in rows)==30 for n in (512,1024,2048))
def fit(rows):
 xs=[r['length'] for r in rows];ys=[r['y_ms'] for r in rows];xm=statistics.mean(xs);ym=statistics.mean(ys);den=sum((x-xm)**2 for x in xs);slope=sum((x-xm)*(y-ym) for x,y in zip(xs,ys))/den;intercept=ym-slope*xm;assert slope>0 and intercept>=0;return intercept,slope
def predict(model,x):return model[0]+model[1]*x
training=[r for r in rows if r['wave']%2==0];holdout=[r for r in rows if r['wave']%2==1];assert len(training)==len(holdout)==45
split=fit(training);allfit=fit(rows);evaluations=[]
for r in holdout:
 old=((r['length']+1)*524288)/(255*1024**3/8)*1000;new=predict(split,r['length']);evaluations.append(dict(r,candidate_ms=new,original_effective_ms=old,candidate_abs_error_ms=abs(new-r['y_ms']),original_abs_error_ms=abs(old-r['y_ms'])))
with (out/'holdout.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(evaluations[0]));w.writeheader();w.writerows(evaluations)
groups=[]
for n in (512,1024,2048):
 subset=[x for x in evaluations if x['length']==n];groups.append({'input_tokens':n,'holdout_count':len(subset),'candidate_mae_ms':statistics.mean(x['candidate_abs_error_ms'] for x in subset),'original_effective_mae_ms':statistics.mean(x['original_abs_error_ms'] for x in subset)})
result={'status':'synchronized_serial_sensitivity_not_frozen','source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'train_count':len(training),'holdout_count':len(holdout),'split_fit_intercept_ms':split[0],'split_fit_ms_per_token':split[1],'all_sample_intercept_ms':allfit[0],'all_sample_ms_per_token':allfit[1],'holdout_groups':groups,'limitations':['Held-out even/odd samples share one service session and are not independent sessions','Source includes explicit per-tensor synchronization, Python, waiting, KV receive and installation; not physical link bandwidth','The original effective transfer parameter omits installation and measures a different benchmark boundary; comparison is boundary diagnostic, not proof of accuracy','Only serial batch 1 and output length 8; no extrapolation beyond measured input lengths','Not fitted from validation completion time, not a common baseline/DAG fee or frozen production model']}
(out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
