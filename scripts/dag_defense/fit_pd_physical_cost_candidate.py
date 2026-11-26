"""Fit a separate provisional serial connector fee from microbenchmarks only."""
import argparse,csv,hashlib,json,pathlib,statistics
p=argparse.ArgumentParser();p.add_argument('--input',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args();a.output.mkdir(exist_ok=False)
raw=a.input.read_bytes();rows=[r for r in csv.DictReader(raw.decode().splitlines()) if r['warmup']=='0']
if len(rows)!=90 or any(sum(int(r['tokens'])==n for r in rows)!=30 for n in (512,1024,2048)):raise ValueError('expected 30 measured observations per shape')
for r in rows:
 n=int(r['tokens']);kv=int(r['kv_bytes']);hidden=int(r['hidden_bytes'])
 if kv!=n*524288 or hidden!=n*8192 or float(r['duration_s'])<=0:raise ValueError('unexpected tensor shape or duration')
train=[r for r in rows if int(r['iteration'])%2==0];hold=[r for r in rows if int(r['iteration'])%2==1]
if any(sum(int(r['tokens'])==n for r in subset)!=15 for n in (512,1024,2048) for subset in (train,hold)):raise ValueError('unexpected split')
def fit(subset):
 xs=[int(r['kv_bytes'])+int(r['hidden_bytes']) for r in subset];ys=[float(r['duration_s']) for r in subset];mx=statistics.mean(xs);my=statistics.mean(ys);slope=sum((x-mx)*(y-my) for x,y in zip(xs,ys))/sum((x-mx)**2 for x in xs);intercept=my-slope*mx
 if slope<=0 or intercept<0:raise ValueError('fit cannot be represented as nonnegative time')
 return {'latency_s':intercept,'bandwidth_bytes_per_s':1/slope}
split_fit=fit(train);full_fit=fit(rows);legacy_bw=255*1024**3/8;out=[]
for r in rows:
 kv=int(r['kv_bytes']);hidden=int(r['hidden_bytes']);actual=float(r['duration_s']);old=(int(r['tokens'])+1)*524288/legacy_bw;new=split_fit['latency_s']+(kv+hidden)/split_fit['bandwidth_bytes_per_s']
 out.append({'tokens':r['tokens'],'iteration':r['iteration'],'split':'train' if r in train else 'holdout','kv_bytes':kv,'hidden_bytes':hidden,'modeled_bulk_bytes':kv+hidden,'measured_s':actual,'legacy_candidate_s':old,'physical_split_fit_s':new,'legacy_absolute_error_s':abs(old-actual),'physical_absolute_error_s':abs(new-actual)})
with (a.output/'samples.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=out[0]);w.writeheader();w.writerows(out)
by=[]
for n in (512,1024,2048):
 rs=[r for r in out if int(r['tokens'])==n and r['split']=='holdout'];by.append({'tokens':n,'heldout_samples':len(rs),'observed_median_s':statistics.median(r['measured_s'] for r in rs),'legacy_mae_s':statistics.mean(r['legacy_absolute_error_s'] for r in rs),'physical_fit_mae_s':statistics.mean(r['physical_absolute_error_s'] for r in rs)})
result={'status':'separate_revised_candidate_not_frozen','input_sha256':hashlib.sha256(raw).hexdigest(),'train_samples':len(train),'holdout_samples':len(hold),'split':'even versus odd iteration, separately represented at each token length','split_fit':split_fit,'all_samples_fit':full_fit,'heldout_by_tokens':by,'limits':['KV plus hidden tensor bytes only; token/ROI/control and framing bytes excluded','Timing includes matching, producer wait, allocation and synchronization; intercept is effective overhead, not isolated physical latency','Microbenchmark uses synthetic tensors, serial single-request transfer and no paged-KV installation','Even/odd split is not an independent repeated session','Do not add hidden bytes to the legacy fitted fee: that would charge them twice','Revised fee must be separately labeled; common baseline/DAG fee remains unchanged','Not calibrated service cost and no validation data used']};(a.output/'candidate.json').write_text(json.dumps(result,indent=2)+'\n')
# The DAG currently bills KV bytes only. Convert the fitted bulk-byte slope to
# an equivalent KV-byte bandwidth for this fixed model, without double counting.
effective_bw=full_fit['bandwidth_bytes_per_s']/(1+8192/524288)
config={'schema_version':'1.2','transfer_start_mode':'decode_pull_candidate','storage_dtype':'float16','capacity_bytes_per_shard':5*1024**3,'bandwidth_bytes_per_s':effective_bw,'latency_s':full_fit['latency_s'],'occupies_gpu':True,'evidence':'separately revised physical KV+hidden serial microbenchmark fit; GPU occupancy is an unvalidated sensitivity assumption','legacy_prefill_billing_extra_token':False}
for n in (512,1024,2048):
 lhs=config['latency_s']+n*524288/config['bandwidth_bytes_per_s'];rhs=full_fit['latency_s']+(n*(524288+8192))/full_fit['bandwidth_bytes_per_s']
 if abs(lhs-rhs)>1e-12:raise ValueError('equivalent KV bandwidth arithmetic mismatch')
(a.output/'revised-dag-candidate.json').write_text(json.dumps(config,indent=2)+'\n');print(json.dumps(result,indent=2))
