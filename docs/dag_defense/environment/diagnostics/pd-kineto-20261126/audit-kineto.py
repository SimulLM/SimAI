import json,pathlib,collections,csv,statistics
p=pathlib.Path(__file__).parent;d=json.loads((p/'producer-kineto-trace.json').read_text());ev=d['traceEvents'];kernels=[x for x in ev if x.get('ph')=='X' and x.get('cat')=='kernel' and x.get('args',{}).get('device')==0];nccl=sorted((x for x in kernels if 'nccl' in x['name'].lower()),key=lambda x:x['ts']);other=sorted((x for x in kernels if 'nccl' not in x['name'].lower()),key=lambda x:x['ts']);intervals=[];pairs=[]
for c in nccl:
 cs,ce=c['ts'],c['ts']+c['dur']
 for k in other:
  ks,ke=k['ts'],k['ts']+k['dur']
  if ks>=ce:break
  if ke<=cs:continue
  start=max(cs,ks);end=min(ce,ke)
  if end>start:
   intervals.append((start,end));pairs.append({'start_us':start,'end_us':end,'overlap_us':end-start,'nccl_start_us':cs,'nccl_duration_us':c['dur'],'nccl_stream':c['args'].get('stream'),'compute_start_us':ks,'compute_duration_us':k['dur'],'compute_name':k['name'],'compute_stream':k['args'].get('stream'),'nccl_correlation':c['args'].get('correlation'),'compute_correlation':k['args'].get('correlation')})
intervals.sort();merged=[]
for a,b in intervals:
 if merged and a<=merged[-1][1]:merged[-1][1]=max(b,merged[-1][1])
 else:merged.append([a,b])
with (p/'kernel-overlap-pairs.csv').open('w',newline='') as f:
 if pairs:
  w=csv.DictWriter(f,fieldnames=list(pairs[0]));w.writeheader();w.writerows(pairs)
status=collections.Counter(str(x.get('status')) for x in [json.loads(line) for line in (p/'client/requests.jsonl').read_text().splitlines()]);out={'requests':sum(status.values()),'status_counts':dict(status),'trace_events':len(ev),'gpu0_kernel_events':len(kernels),'gpu0_nccl_kernels':len(nccl),'gpu0_non_nccl_kernels':len(other),'nccl_context_stream_counts':{str(k):v for k,v in collections.Counter((x['args'].get('context'),x['args'].get('stream')) for x in nccl).items()},'non_nccl_context_stream_counts':{str(k):v for k,v in collections.Counter((x['args'].get('context'),x['args'].get('stream')) for x in other).items()},'overlap_pairs':len(pairs),'distinct_nccl_kernels_with_overlap':len({(x['nccl_start_us'],x['nccl_correlation']) for x in pairs}),'distinct_compute_kernels_with_overlap':len({(x['compute_start_us'],x['compute_correlation']) for x in pairs}),'merged_overlap_interval_count':len(merged),'union_overlap_us':sum(b-a for a,b in merged),'max_pair_overlap_us':max((x['overlap_us'] for x in pairs),default=0),'different_stream_pairs':sum(x['nccl_stream']!=x['compute_stream'] for x in pairs),'top_compute_names':collections.Counter(x['compute_name'] for x in pairs).most_common(8),'trace_time_unit':'microseconds (Chrome trace)','limits':['Kineto instrumentation perturbs execution; not formal E2E or calibrated cost','CUDA kernel intervals from profiler may include scheduling/residency gaps; timestamp overlap does not quantify simultaneous SM use or establish a safe constant occupancy fraction','Captures one producer process and one diagnostic 2048/8 workload; does not establish behavior for all load shapes','CUDA profiler timeline itself is relative trace time; no claim of exact monotonic host clock conversion','NCCL kernels are classified by name, no individual request or tensor payload mapping']};(p/'kernel-overlap-audit.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
