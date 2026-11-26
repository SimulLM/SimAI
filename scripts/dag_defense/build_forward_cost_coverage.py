"""Inventory independently observed whole-forward shapes; do not extrapolate."""
import csv,hashlib,json,pathlib,sys
base=pathlib.Path(sys.argv[1]);bins=pathlib.Path(sys.argv[2]);out=pathlib.Path(sys.argv[3]);out.mkdir(parents=True,exist_ok=False)
with base.open() as f:base_rows=list(csv.DictReader(f))
with bins.open() as f:bin_rows=list(csv.DictReader(f))
index={}
for x in base_rows:
 key=(x['nature'],int(x['input_tokens']),int(x['actual_batch']))
 if key in index:raise ValueError('duplicate base shape')
 if int(x['warmup_waves'])<10 or int(x['measured_waves'])<30:raise ValueError('unqualified shape')
 index[key]=x
bin_index={}
for x in bin_rows:
 key=(int(x['input_tokens']),int(x['actual_batch']),int(x['rounded_mean_context']),int(x['mixed_context']))
 if key in bin_index:raise ValueError('duplicate context shape')
 if x['eligible']!='1' or int(x['warmup_waves'])<10 or int(x['measured_waves'])<30:raise ValueError('unqualified bin')
 bin_index[key]=x
rows=[]
for length in (1024,2048):
 for batch in (1,2,3,4):
  reachable=length*batch<=4096;key=('producer_prefill',length,batch);x=index.get(key)
  rows.append({'phase':'prefill','input_tokens':length,'batch':batch,'rounded_context':'','context_type':'','status':'covered' if x else 'unreachable_token_cap' if not reachable else 'missing','source_ms':x['median_of_wave_medians_ms'] if x else ''})
  for ctx in range(length+16,length+129,16):
   for mixed in (0,1):
    x=bin_index.get((length,batch,ctx,mixed));rows.append({'phase':'decode','input_tokens':length,'batch':batch,'rounded_context':ctx,'context_type':'mixed' if mixed else 'uniform','status':'covered' if x else 'not_applicable_single_sequence' if mixed and batch==1 else 'missing','source_ms':x['median_forward_ms'] if x else ''})
with (out/'coverage.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
summary={'status':'candidate_whole_forward_coverage_incomplete','rows':len(rows),'prefill_covered':sum(x['phase']=='prefill' and x['status']=='covered' for x in rows),'prefill_missing':sum(x['phase']=='prefill' and x['status']=='missing' for x in rows),'prefill_unreachable':sum(x['phase']=='prefill' and x['status']=='unreachable_token_cap' for x in rows),'decode_covered':sum(x['phase']=='decode' and x['status']=='covered' for x in rows),'decode_missing':sum(x['phase']=='decode' and x['status']=='missing' for x in rows),'decode_not_applicable':sum(x['phase']=='decode' and x['status']=='not_applicable_single_sequence' for x in rows),'source_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (base,bins)},'limitations':['Uniform and mixed shapes are kept separate; not all are necessarily reached by the chosen workload','Round-up bins are observed summaries, not exact context interpolation','Whole-forward events exclude KV, logits, sampler, CPU and router and may include stream gaps','No 512-token decode context-bin table; single-request calibration needs separate coverage','Candidate is not a simulator implementation, frozen fee, or formal validation']};(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
