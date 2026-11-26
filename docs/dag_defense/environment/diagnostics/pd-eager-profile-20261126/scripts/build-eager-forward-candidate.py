"""Select independently warmed, wave-balanced forward timings; not frozen fees."""
import collections,csv,hashlib,json,statistics
from pathlib import Path
root=Path('/root/autodl-tmp/dag-handoff/runs'); sources={'main':root/'pd-mapped-eager-audit-20261126/mapped.csv','b4':root/'pd-mapped-eager-b4-audit-20261126/mapped.csv'}; out=root/'pd-eager-forward-candidate-20261126';out.mkdir(exist_ok=False)
need=[('producer_prefill',n,b) for n in (512,1024) for b in (1,2,3,4)]+[('producer_prefill',2048,b) for b in (1,2)]+[('consumer_decode',n,b) for n in (512,575,1024,1151,2048,2175) for b in (1,2,3,4)]
groups=collections.defaultdict(lambda:collections.defaultdict(list))
for source,p in sources.items():
 for r in csv.DictReader(open(p)):
  k=(r['nature'],int(r['input_tokens']),int(r['actual_batch'])); wave=(int(r['wave_batch']),int(r['wave'])); groups[(source,k)][(r['warmup']=='True',wave)].append(float(r['forward_ms']))
rows=[]; missing=[]
for k in need:
 candidates=[]
 for source in sources:
  v=groups[(source,k)]; warm=[w for (w,_) in v if w]; measurements=[statistics.median(x) for (w,_),x in v.items() if not w]
  if len(warm)>=10 and len(measurements)>=30:candidates.append((len(measurements),source,len(warm),measurements))
 if not candidates:missing.append(k);continue
 count,source,warm,values=max(candidates,key=lambda x:(x[0],x[1]=='main'));rows.append({'nature':k[0],'input_tokens':k[1],'actual_batch':k[2],'source':source,'warmup_waves':warm,'measured_waves':count,'median_of_wave_medians_ms':statistics.median(values),'context_note':'decode context spans input through input+7 tokens' if source=='b4' and k[0]=='consumer_decode' else 'profile input and first decode step'})
with (out/'forward-cost.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
manifest={'status':'candidate_not_frozen' if not missing else 'blocked','required_points':len(need),'selected_points':len(rows),'missing':missing,'selection':'for each shape choose one source with >=10 distinct warmup waves and >=30 distinct measured waves; maximum measured waves; median per wave then median across waves','sources':{k:{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for k,p in sources.items()},'limitations':['forward only; excludes KV, logits, sampling, CPU and router','b4 supplement uses context range input to input+7; not exact endpoint','eager execution, synchronization perturbs load','not a parameter freeze; interpolation and independent cost accounting not yet established']};(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(manifest,indent=2))
