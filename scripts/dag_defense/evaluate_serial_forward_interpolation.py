"""Evaluate independent whole-forward interpolation on one calibration trace."""
import csv,hashlib,json,pathlib,statistics,sys
profile=pathlib.Path(sys.argv[1]);trace=pathlib.Path(sys.argv[2]);out=pathlib.Path(sys.argv[3]);out.mkdir(parents=True,exist_ok=False)
with profile.open() as f:src=list(csv.DictReader(f))
anchor={}
for n in (512,575):
 matched=[x for x in src if x['nature']=='consumer_decode' and int(x['input_tokens'])==n and int(x['actual_batch'])==1];assert len(matched)==1 and int(matched[0]['warmup_waves'])>=10 and int(matched[0]['measured_waves'])>=30;anchor[n]=float(matched[0]['median_of_wave_medians_ms'])
with trace.open() as f:rows=list(csv.DictReader(f))
assert len(rows)==63 and [int(x['context_tokens']) for x in rows]==list(range(513,576))
output=[]
for r in rows:
 x=int(r['context_tokens']);obs=float(r['gpu_forward_ms']);old=float(r['simulated_layer_sum_ms']);candidate=anchor[512]+(anchor[575]-anchor[512])*(x-512)/(575-512)
 output.append({'iteration':int(r['iteration']),'context_tokens':x,'observed_full_forward_ms':obs,'old_layer_sum_ms':old,'candidate_whole_forward_ms':candidate,'old_abs_error_ms':abs(old-obs),'candidate_abs_error_ms':abs(candidate-obs)})
with (out/'iterations.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(output[0]));w.writeheader();w.writerows(output)
summary={'status':'single_request_forward_only_sensitivity','anchor_ms':anchor,'old_mae_ms':statistics.mean(x['old_abs_error_ms'] for x in output),'candidate_mae_ms':statistics.mean(x['candidate_abs_error_ms'] for x in output),'old_signed_error_median_ms':statistics.median(x['old_layer_sum_ms']-x['observed_full_forward_ms'] for x in output),'candidate_signed_error_median_ms':statistics.median(x['candidate_whole_forward_ms']-x['observed_full_forward_ms'] for x in output),'iterations':len(output),'source_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (profile,trace)},'limitations':['One evaluation request with 63 correlated steps; not independent holdout sessions','Measurement hooks and synchronization perturb GPU forward timings','Full-forward versus layer-sum boundaries differ; candidate replaces layer sum and must never be added to it','Anchors belong to different profiling requests and contain only approximate context semantics; no extrapolation','Only serial batch 1 512/64 diagnostic, not a full simulator run, formal validation, frozen fee or E2E accuracy']};(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
