import csv,json,pathlib,statistics,collections
p=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/kv-overlap-matchfirst-20261126');rows={r:list(csv.DictReader((p/f'rank{r}.csv').open())) for r in (0,1)};summary=[];errors=[]
for r in (0,1):
 for mode in ('compute_only','transfer_only','concurrent'):
  data=[x for x in rows[r] if x['mode']==mode and x['warmup']=='0'];h=[(int(x['host_end_ns'])-int(x['host_start_ns']))/1e6 for x in data];g=[float(x['compute_gpu_ms']) for x in data if x['compute_gpu_ms']]
  if len(data)!=30:errors.append({'rank':r,'mode':mode,'count':len(data)})
  if r==1 and mode!='compute_only' and any(x['integrity']!='1' for x in data):errors.append({'rank':r,'mode':mode,'error':'payload endpoint sample mismatch'})
  summary.append({'rank':r,'mode':mode,'n':len(data),'host_median_ms':statistics.median(h) if h else None,'compute_gpu_median_ms':statistics.median(g) if g else None,'sampled_integrity':'pass' if r==1 and mode!='compute_only' and all(x['integrity']=='1' for x in data) else 'not_applicable'})
index={(int(x['rank']),x['mode'],x['iteration']):x for rr in rows.values() for x in rr};unions=[]
for i in range(10,40):
 a=index[(0,'concurrent',str(i))];b=index[(1,'concurrent',str(i))];unions.append((max(int(a['host_end_ns']),int(b['host_end_ns']))-min(int(a['host_start_ns']),int(b['host_start_ns'])))/1e6)
out={'status':'microbenchmark_pass' if not errors else 'failed','summary':summary,'concurrent_host_union_median_ms':statistics.median(unions),'errors':errors,'limits':['synthetic GEMM plus vLLM SimpleBuffer token lookup; compute starts after matched signal, not real model forward','host synchronization windows do not identify exact GPU overlap start/end','GPU kernel timing can include scheduling and contention','token IDs and ROI plus samples of key/value/hidden were checked, not full KV payload','fixed sequence of modes and synchronization perturb normal execution']};matched=[x for x in rows[0] if x['mode']=='concurrent' and x['warmup']=='0']
ok=sum(bool(x['matched_ns']) and int(x['host_start_ns'])<=int(x['matched_ns'])<=int(x['host_end_ns']) for x in matched)
out['match_order']={'valid':ok,'total':len(matched)}
if ok!=30 or len(matched)!=30:out['errors'].append({'error':'match ordering','valid':ok,'total':len(matched)});out['status']='failed'
(p/'audit.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))

