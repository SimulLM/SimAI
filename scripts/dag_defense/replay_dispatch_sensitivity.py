"""Replay six short instrumented real waves for batching diagnosis, not validation."""
import collections,concurrent.futures,csv,hashlib,json,os,pathlib,shutil,sys
from scripts.dag_defense import replay_calibration_arrivals_v3 as core
from scripts.dag_phase4.main import write_csv,write_json
from scripts.dag_phase6.main import pd_command
root=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/real-batch-dispatch-sensitivity-v2-20261126');root.mkdir(exist_ok=False);core.OUT=root
profile=root/'profile';profile.mkdir()
for n in ('compute.csv','cpu.csv','network.csv'):shutil.copy2(core.PROFILE/n,profile/n)
shutil.copy2('/root/autodl-tmp/dag-handoff/runs/pd-batch3-shape-aware-profile-20261126/attention.csv',profile/'attention.csv');core.PROFILE=profile
cfg=root/'pd-config.json';write_json(cfg,dict(schema_version='1.2',transfer_start_mode='decode_pull_candidate',storage_dtype='float16',capacity_bytes_per_shard=5*1024**3,bandwidth_bytes_per_s=255*1024**3/8,latency_s=0,occupies_gpu=True,evidence='instrumented real-wave scheduling diagnostic; not frozen',legacy_prefill_billing_extra_token=True))
source=core.ROOT/'docs/dag_defense/environment/diagnostics/pd-flow-boundary-20261126/derived-boundaries.csv';rows=[r for r in csv.DictReader(source.open()) if r['warmup']=='False' and r['wave']=='10'];cases=collections.defaultdict(list)
for r in rows:cases[(int(r['input_tokens']),int(r['requested_batch']))].append(r)
jobs=[]
for (length,concurrency),items in sorted(cases.items()):
 if len(items)!=concurrency:raise ValueError('incomplete selected wave')
 items.sort(key=lambda r:(int(r['arrival_ns']),r['router_id']));case=root/f'in{length}-c{concurrency}';case.mkdir();first=int(items[0]['arrival_ns']);trace=case/'trace.csv';write_csv(trace,[dict(arrived_at=(int(r['arrival_ns'])-first)/1e9,num_prefill_tokens=length,num_decode_tokens=8) for r in items]);write_json(case/'request-map.json',[dict(simulator_request_id=i,router_id=r['router_id'],prefill_id=r['prefill_id'],decode_id=r['decode_id'],arrival_ns=int(r['arrival_ns']),completion_ns=int(r['router_complete_ns'])) for i,r in enumerate(items)])
 shutil.copytree(pathlib.Path('/root/autodl-tmp/dag-handoff/runs/real-batch-diagnostic-20261126')/case.name/'adapted_baseline',case/'adapted_baseline')
 for mode,cwd,pd in [('dag',core.ROOT,True)]:
  dest=case/mode;cfg=case/'pd-config.json';write_json(cfg,dict(schema_version='1.3',transfer_start_mode='decode_pull_candidate',decode_dispatch_delay_s={1024:0.0045259245,2048:0.0063988115}[length],storage_dtype='float16',capacity_bytes_per_shard=5*1024**3,bandwidth_bytes_per_s=255*1024**3/8,latency_s=0,occupies_gpu=True,evidence='serial instrumented host interval sensitivity; not frozen',legacy_prefill_billing_extra_token=True));cmd=core.patch(pd_command(dest,root/'profiles',trace,cfg),dest,trace,pd)
  indices=[i for i,x in enumerate(cmd) if x=='--dag_pd_config'];
  for i in indices:cmd[i+1]=str(cfg)
  for flag,val in [('--trace_request_generator_config_max_tokens','2056'),('--random_forrest_execution_time_predictor_config_prediction_max_prefill_chunk_size','4096')]:cmd[cmd.index(flag)+1]=val
  if not pd:
   cmd+=['--replica_config_pd_p2p_comm_bandwidth','255']
   for option in ('--execution_mode','--dag_pd_config'):
    if option in cmd:i=cmd.index(option);del cmd[i:i+2]
   for flag in ('--metrics_config_write_json_trace','--metrics_config_enable_chrome_trace'):
    if flag in cmd:cmd.remove(flag)
  jobs.append((case.name,mode,cwd,cmd,dest,length,concurrency))
if len(jobs)!=6:raise ValueError('expected six DAG cases')
(root/'manifest.json').write_text(json.dumps({'status':'diagnostic_not_frozen','source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'selection':'wave 10 of 30 measured; six requested shapes; instrumented 8-output request traces','formal_validation':False,'adapted_baseline':'reused from prior identical-arrival diagnostic, not rerun','dispatch_delay':'independent serial instrumented median 1024=0.0045259245s, 2048=0.0063988115s'},indent=2)+'\n')
def run(job):
 case,mode,cwd,cmd,dest,length,concurrency=job
 try:
  code=core.run(cwd,cmd,dest)
  if code==0:
   files=list(dest.glob('*/request_metrics.csv'))
   if len(files)!=1:raise ValueError('request metrics missing')
   metrics=list(csv.DictReader(files[0].open()))
   if len(metrics)!=concurrency or any(float(r['request_num_prefill_tokens'])!=length or float(r['request_num_decode_tokens'])!=8 for r in metrics):raise ValueError('effective request length mismatch')
  return {'case':case,'role':mode,'exit':code}
 except Exception as e:return {'case':case,'role':mode,'exit':-1,'error':repr(e)}
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
 futures=[pool.submit(run,j) for j in jobs]
 for f in concurrent.futures.as_completed(futures):
  r=f.result()
  with (root/'progress.jsonl').open('a') as h:h.write(json.dumps(r)+'\n');h.flush();os.fsync(h.fileno())
  print(json.dumps(r),flush=True)
results=[json.loads(x) for x in (root/'progress.jsonl').read_text().splitlines()];status={'status':'completed' if len(results)==6 and all(r['exit']==0 for r in results) else 'failed','results':results,'formal_validation':False};write_json(root/'status.json',status);sys.exit(status['status']!='completed')
