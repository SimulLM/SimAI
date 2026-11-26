import pathlib,json,collections,csv
p=pathlib.Path(__file__).parent;rows=[];issues=[]
for file in sorted(p.glob('kineto-trace-*.json')):
 pid=int(file.stem.split('-')[-1]);data=json.load(file.open());events=data['traceEvents'];ks=[e for e in events if e.get('cat')=='kernel' and e.get('ph')=='X' and e.get('args',{}).get('device')==0];nccl=sorted([e for e in ks if 'nccl' in e['name'].lower()],key=lambda e:e['ts']);other=sorted([e for e in ks if 'nccl' not in e['name'].lower()],key=lambda e:e['ts']);pairs=[];j=0
 for c in nccl:
  cs=c['ts'];ce=cs+c['dur']
  while j<len(other) and other[j]['ts']+other[j]['dur']<=cs:j+=1
  k=j
  while k<len(other) and other[k]['ts']<ce:
   o=other[k];amt=min(ce,o['ts']+o['dur'])-max(cs,o['ts'])
   if amt>0:pairs.append({'trace_pid':pid,'nccl_ts_us':cs,'nccl_dur_us':c['dur'],'nccl_stream':c['args'].get('stream'),'other_ts_us':o['ts'],'other_dur_us':o['dur'],'other_stream':o['args'].get('stream'),'overlap_us':amt,'other_name':o['name']})
   k+=1
 control=[json.loads(x) for x in (p/f'profiler-control-{pid}.jsonl').read_text().splitlines()];rows.append({'trace_pid':pid,'trace_file':file.name,'event_count':len(events),'nccl_kernel_count':len(nccl),'other_kernel_count':len(other),'nccl_context_streams':dict(collections.Counter(str((x['args'].get('context'),x['args'].get('stream'))) for x in nccl)),'other_context_streams':dict(collections.Counter(str((x['args'].get('context'),x['args'].get('stream'))) for x in other)),'overlap_pairs':len(pairs),'different_stream_pairs':sum(x['nccl_stream']!=x['other_stream'] for x in pairs),'max_overlap_us':max((x['overlap_us'] for x in pairs),default=0),'control':control});
 with (p/f'kernel-pairs-{pid}.json').open('w') as f:json.dump(pairs,f,indent=2)
 if len(nccl)==0 or len(other)==0 or not any(x.get('event')=='finished' for x in control):issues.append({'pid':pid,'error':'missing kernels or profiler finish'})
requests=[json.loads(x) for x in (p/'client/requests.jsonl').read_text().splitlines()];out={'status':'diagnostic_complete' if len(rows)==2 and not issues and len(requests)==104 and all(x.get('status')==200 for x in requests) else 'incomplete','requests':len(requests),'status_counts':dict(collections.Counter(str(x.get('status')) for x in requests)),'traces':rows,'issues':issues,'limits':['Each process sees its assigned physical GPU as CUDA device 0; infer producer/consumer from corresponding worker logs, not device index alone','Trace captured GPU kernels only in profiler windows; no exact individual request or payload attribution','Profiler instrumentation and export perturb execution and output length is 8; not formal E2E','same-stream submicrosecond timestamp overlaps can be boundary artifacts; no independent SM occupancy measurement','does not imply both GPUs are exclusively occupied over entire host-level transfer']};(p/'both-audit.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
