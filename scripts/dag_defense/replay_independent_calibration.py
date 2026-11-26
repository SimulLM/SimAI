"""Replay existing calibration arrivals against candidate simulators, never validation."""
import collections,concurrent.futures,csv,hashlib,json,os,pathlib,shutil,subprocess,sys,time
from scripts.dag_defense import replay_calibration_arrivals_v3 as core
from scripts.dag_phase4.main import write_csv,write_json
from scripts.dag_phase6.main import pd_command
out=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/pd-pull-calibration-replay-20261126');out.mkdir(exist_ok=False);core.OUT=out
profile=out/'profile';profile.mkdir()
for name in ('compute.csv','cpu.csv','network.csv'):shutil.copy2(core.PROFILE/name,profile/name)
shutil.copy2('/root/autodl-tmp/dag-handoff/runs/pd-batch3-shape-aware-profile-20261126/attention.csv',profile/'attention.csv');core.PROFILE=profile
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest(); cfg=out/'pd-config.json';write_json(cfg,dict(schema_version='1.2',transfer_start_mode='decode_pull_candidate',storage_dtype='float16',capacity_bytes_per_shard=5*1024**3,bandwidth_bytes_per_s=255*1024**3/8,latency_s=0,occupies_gpu=True,evidence='candidate independent calibration replay; not frozen',legacy_prefill_billing_extra_token=True))
inputs=[];jobs=[];sources={}; statuses=out/'progress.jsonl'
for mode in ('serial','concurrent'):
 source=pathlib.Path('/root/autodl-tmp/dag-handoff/runs')/f'calibration-{mode}-independent-20261126'
 for rep in range(3):
  client=source/f'client-{rep}/requests.jsonl';router=source/f'server-{rep}/router-events.jsonl';sources[str(client)]=sha(client);sources[str(router)]=sha(router)
  records=[json.loads(x) for x in client.read_text().splitlines() if x];events=collections.defaultdict(lambda:collections.defaultdict(list))
  for line in router.read_text().splitlines():
   e=json.loads(line);events[e['request_id']][e['event']].append(e)
  selected=[r for r in records if not r['warmup']]
  if len(selected)!=32:raise ValueError(f'expected 32 measured requests: {mode} {rep}')
  matched=[]
  for r in selected:
   ev=events[r['router_id']];names=('server_arrival','server_complete','decode_mapping')
   if any(len(ev[x])!=1 for x in names) or r['status']!=200 or not r['done'] or r['usage']['prompt_tokens']!=512 or r['usage']['completion_tokens']!=64:raise ValueError('incomplete calibration request')
   if ev['decode_mapping'][0]['backend_request_id']!=r['decode_id'] or any(ev[n][0]['clock_id']!='CLOCK_MONOTONIC' for n in names):raise ValueError('request mapping or clock mismatch')
   a=ev['server_arrival'][0]['timestamp_ns'];z=ev['server_complete'][0]['timestamp_ns']
   if z<a:raise ValueError('clock order invalid')
   digest=hashlib.sha256(json.dumps(r['input_ids'],separators=(',',':')).encode()).hexdigest()
   if digest!=r['input_sha256'] or len(r['input_ids'])!=512:raise ValueError('input mismatch')
   matched.append((a,z,r))
  matched.sort(key=lambda x:(x[0],x[2]['router_id'])); origin=matched[0][0];case=out/f'{mode}-{rep}';case.mkdir();trace=case/'trace.csv';write_csv(trace,[{'arrived_at':(a-origin)/1e9,'num_prefill_tokens':512,'num_decode_tokens':64} for a,z,r in matched]);mapping=[{'simulator_request_id':i,'router_id':r['router_id'],'input_sha256':r['input_sha256'],'server_arrival_ns':a,'server_complete_ns':z,'server_e2e_s':(z-a)/1e9} for i,(a,z,r) in enumerate(matched)];write_json(case/'request-map.json',mapping)
  inputs.append({'case':case.name,'trace_sha256':sha(trace),'request_map_sha256':sha(case/'request-map.json'),'requests':len(mapping)})
  for name,cwd,pd in [('dag',core.ROOT,True),('adapted_baseline',core.BASE,False)]:
   dest=case/name;cmd=core.patch(pd_command(dest,out/'profiles',trace,cfg),dest,trace,pd)
   if not pd:
    cmd+=['--replica_config_pd_p2p_comm_bandwidth','255']
    for option in ('--execution_mode','--dag_pd_config'):
     if option in cmd:i=cmd.index(option);del cmd[i:i+2]
    for flag in ('--metrics_config_write_json_trace','--metrics_config_enable_chrome_trace'):
     if flag in cmd:cmd.remove(flag)
   jobs.append((case.name,name,cwd,cmd,dest))
write_json(out/'manifest.json',{'status':'diagnostic_not_frozen','cases':inputs,'source_hashes':sources,'profile_hashes':{p.name:sha(p) for p in profile.iterdir()},'pd_config_sha256':sha(cfg),'note':'Actual router arrival replay; calibration only; candidate costs and boundary semantics unverified. Adapted baseline, not untouched original.'})
def execute(job):
 case,name,cwd,cmd,dest=job
 try:code=core.run(cwd,cmd,dest);message=''
 except Exception as e:code=-1;message=repr(e)
 return {'case':case,'simulator':name,'exit_code':code,'error':message,'finished_unix_s':time.time()}
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
 futures=[pool.submit(execute,j) for j in jobs]
 for f in concurrent.futures.as_completed(futures):
  result=f.result()
  with statuses.open('a') as h:h.write(json.dumps(result)+'\n');h.flush();os.fsync(h.fileno())
  print(json.dumps(result),flush=True)
results=[json.loads(x) for x in statuses.read_text().splitlines()];write_json(out/'status.json',{'status':'completed' if len(results)==12 and all(x['exit_code']==0 for x in results) else 'failed','runs':len(results),'failed':[x for x in results if x['exit_code']!=0],'formal_validation':False});sys.exit(0 if len(results)==12 and all(x['exit_code']==0 for x in results) else 1)
