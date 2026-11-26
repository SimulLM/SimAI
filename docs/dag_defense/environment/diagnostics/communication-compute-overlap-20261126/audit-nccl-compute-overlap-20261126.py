import csv,json,pathlib,statistics,collections
p=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/nccl-compute-overlap-20261126');rows={r:list(csv.DictReader((p/f'rank{r}.csv').open())) for r in (0,1)};summary=[];errors=[]
for r in (0,1):
 for mode in ('compute_only','transfer_only','concurrent'):
  data=[x for x in rows[r] if x['mode']==mode and x['warmup']=='0'];h=[(int(x['host_end_ns'])-int(x['host_start_ns']))/1e6 for x in data];g=[float(x['compute_gpu_ms']) for x in data if x['compute_gpu_ms']]
  if len(data)!=30:errors.append({'rank':r,'mode':mode,'count':len(data)})
  if r==1 and mode!='compute_only' and any(x['integrity']!='1' for x in data):errors.append({'rank':r,'mode':mode,'error':'payload endpoint sample mismatch'})
  summary.append({'rank':r,'mode':mode,'n':len(data),'host_median_ms':statistics.median(h) if h else None,'compute_gpu_median_ms':statistics.median(g) if g else None,'sampled_integrity':'pass' if r==1 and mode!='compute_only' and all(x['integrity']=='1' for x in data) else 'not_applicable'})
index={(int(x['rank']),x['mode'],x['iteration']):x for rr in rows.values() for x in rr};unions=[]
for i in range(10,40):
 a=index[(0,'concurrent',str(i))];b=index[(1,'concurrent',str(i))];unions.append((max(int(a['host_end_ns']),int(b['host_end_ns']))-min(int(a['host_start_ns']),int(b['host_start_ns'])))/1e6)
out={'status':'microbenchmark_pass' if not errors else 'failed','summary':summary,'concurrent_host_union_median_ms':statistics.median(unions),'errors':errors,'limits':['synthetic FP16 GEMM and single NCCL tensor, not vLLM connector or model forward','host synchronization windows do not identify exact GPU overlap start/end','GPU kernel timing can include scheduling and contention','integrity sampled first/last payload values, not full payload','fixed sequence of modes and synchronization perturb normal execution']};(p/'audit.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
