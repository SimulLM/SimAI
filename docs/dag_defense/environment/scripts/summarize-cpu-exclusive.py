import argparse,collections,csv,glob,json,statistics
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--run-dir',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--clients',type=Path,nargs='+');a=p.parse_args();r=a.run_dir;a.output.mkdir(parents=True,exist_ok=False)
requests={}
for client in (a.clients or [r]):
 spec=json.loads((client/'client-spec.json').read_text()); start_count=len(requests)
 for line in (client/'client-requests.jsonl').read_text().splitlines():
  x=json.loads(line);assert x['status']==200 and 'error' not in x and x['usage']['prompt_tokens']==x['length'] and x['usage']['completion_tokens']==2
  rid=x['request_id']+'-0';assert rid not in requests;x['source']=client.name;requests[rid]=x
 assert len(requests)-start_count==sum((spec['warmup_waves']+spec['measured_waves'])*b for _ in spec['lengths'] for b in spec['batches']) and (client/'client-exit-code').read_text().strip()=='0'
events=[]
for p in glob.glob(str(r/'cpu-events-*.jsonl')):
 events.extend(json.loads(x) for x in Path(p).read_text().splitlines())
events.sort(key=lambda x:x['start_ns']); names=('schedule','prepare_inputs','sampler_synchronized','process_model_outputs');warm=collections.Counter();measured=collections.defaultdict(list);membership=collections.Counter();samples=[];unknown=0;mixed=0
for e in events:
 assert e['event'] in names and e['duration_ns']==e['end_ns']-e['start_ns'] and e['duration_ns']>=0
 gs=e['groups'];ids=[x['request_id'] for x in gs]; rs=[requests.get(i) for i in ids]
 if any(x is None for x in rs):unknown+=1;continue
 for g in gs:membership[(g['request_id'],g['is_prompt'],e['event'])]+=1
 if len({(x['source'],x['length'],x['batch'],x['wave'],x['warmup']) for x in rs})!=1 or len({g['is_prompt'] for g in gs})!=1:mixed+=1;continue
 x=rs[0];phase='prefill' if gs[0]['is_prompt'] else 'decode';key=(e['event'],phase,x['length'],len(gs))
 if x['warmup']:warm[key]+=1;eligible=False
 else:
  eligible=warm[key]>=10
  if eligible:measured[key].append(e['duration_ns']/1e6)
 samples.append(dict(event=e['event'],phase=phase,input_tokens=x['length'],actual_batch=len(gs),requested_batch=x['batch'],source=x['source'],wave=x['wave'],warmup=int(x['warmup']),eligible=int(eligible),start_ns=e['start_ns'],duration_ns=e['duration_ns'],request_ids='|'.join(ids)))
missing=[(rid,phase,name) for rid in requests for phase in (True,False) for name in names if membership[(rid,phase,name)]!=1]
assert not missing and not mixed,(len(missing),mixed)
summary=[]
for (op,phase,n,b),vals in sorted(measured.items()):
 vals.sort();summary.append(dict(event=op,phase=phase,input_tokens=n,actual_batch=b,warmups_seen=warm[(op,phase,n,b)],eligible_samples=len(vals),median_ms=statistics.median(vals),p95_ms=vals[max(0,(95*len(vals)+99)//100-1)]))
for filename,rows in [('samples.csv',samples),('summary.csv',summary)]:
 with (a.output/filename).open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
report=dict(requests=len(requests),unmapped_events=unknown,mixed_events=mixed,missing_or_repeated_memberships=len(missing),profiled_events=len(samples),qualified_shapes=sum(x['eligible_samples']>=30 for x in summary),partial_shapes=sum(x['eligible_samples']<30 for x in summary),method='host monotonic timing with CUDA synchronization immediately before and after sampler, diagnostic only')
(a.output/'coverage.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
