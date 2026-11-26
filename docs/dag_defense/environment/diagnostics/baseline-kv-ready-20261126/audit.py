import csv,glob,json,pathlib,collections,statistics
root=pathlib.Path(__file__).parent
paths={'original':pathlib.Path('/root/autodl-tmp/dag-handoff/runs/pristine-real-arrival-20261126/concurrent-0/baseline'),'corrected':root/'corrected','dag':pathlib.Path('/root/autodl-tmp/dag-handoff/runs/pristine-real-arrival-20261126/concurrent-0/dag')}
results={};maps=json.loads(pathlib.Path('/root/autodl-tmp/dag-handoff/runs/pd-pull-calibration-replay-20261126/concurrent-0/request-map.json').read_text())
for mode,p in paths.items():
 assert (p/'exit').read_text().strip()=='0';files=list(p.glob('2026*/request_metrics.csv'));assert len(files)==1
 metrics={int(x['Request Id']):x for x in csv.DictReader(files[0].open())};assert len(metrics)==32
 trace=list(p.glob('2026*/chrome_trace.json'));assert len(trace)==1
 ev=[x for x in json.loads(trace[0].read_text())['traceEvents'] if x.get('ph')=='X' and x.get('pid')==1 and x.get('args',{}).get('request_ids')];ev.sort(key=lambda x:x['ts'])
 violations=[]
 for e in ev:
  for rid in e['args']['request_ids']:
   ready=float(metrics[int(rid)]['decode_arrived_at']);start=e['ts']/1e6
   if start+1e-12<ready:violations.append({'request_id':rid,'start_s':start,'modeled_ready_s':ready,'early_ms':(ready-start)*1000})
 results[mode]={'requests':len(metrics),'decode_batches':len(ev),'premature_batch_memberships':len(violations),'affected_requests':len({x['request_id'] for x in violations}),'max_early_ms':max((x['early_ms'] for x in violations),default=0),'first_batches':[{'start_ms':x['ts']/1000,'request_ids':x['args']['request_ids']} for x in ev[:4]],'mean_absolute_error_ms':statistics.mean(abs(float(metrics[x['simulator_request_id']]['request_e2e_time'])-x['server_e2e_s'])*1000 for x in maps),'violations':violations}
 assert len(maps)==32
(root/'audit'/'summary.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps({k:{key:v for key,v in x.items() if key!='violations'} for k,x in results.items()},indent=2))
