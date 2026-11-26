"""Diagnostic only: exercise shape-aware candidate with both adapted simulators."""
import json,os,pathlib,shutil,sys
from scripts.dag_defense import replay_calibration_arrivals_v3 as core
from scripts.dag_phase4.main import write_csv,write_json
from scripts.dag_phase6.main import pd_command
out=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/pd-decode-pull-interleave-smoke-20261126');out.mkdir(exist_ok=False);core.OUT=out
profile=out/'profile';profile.mkdir()
for name in ('compute.csv','cpu.csv','network.csv'):shutil.copy2(core.PROFILE/name,profile/name)
shutil.copy2('/root/autodl-tmp/dag-handoff/runs/pd-batch3-shape-aware-profile-20261126/attention.csv',profile/'attention.csv');core.PROFILE=profile
trace=out/'requests.csv';write_csv(trace,[{'arrived_at':t,'num_prefill_tokens':1024,'num_decode_tokens':128} for t in (0,0.10)])
cfg=out/'pd-config.json';write_json(cfg,dict(schema_version='1.2',transfer_start_mode='decode_pull_candidate',storage_dtype='float16',capacity_bytes_per_shard=5*1024**3,bandwidth_bytes_per_s=255*1024**3/8,latency_s=0,occupies_gpu=True,evidence='decode pull candidate diagnostic only; not frozen',legacy_prefill_billing_extra_token=True))
codes={}
for name,cwd,pd in [('dag',core.ROOT,True),('adapted_baseline',core.BASE,False)]:
 dest=out/name;cmd=core.patch(pd_command(dest,out/'profiles',trace,cfg),dest,trace,pd)
 if not pd:
  cmd += ['--replica_config_pd_p2p_comm_bandwidth','255']
  for option in ('--execution_mode','--dag_pd_config'):
   if option in cmd:i=cmd.index(option);del cmd[i:i+2]
  for flag in ('--metrics_config_write_json_trace','--metrics_config_enable_chrome_trace'):
   if flag in cmd:cmd.remove(flag)
 codes[name]=core.run(cwd,cmd,dest)
(out/'status.json').write_text(json.dumps({'status':'diagnostic_only','codes':codes,'note':'synthetic arrivals; candidate fees; not calibration, validation, or proof of scheduling parity'},indent=2)+'\n');print(codes);sys.exit(0 if all(v==0 for v in codes.values()) else 1)
