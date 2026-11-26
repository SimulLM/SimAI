import json,os,sys,importlib.util
from pathlib import Path
s=Path('/root/autodl-tmp/dag-handoff/scripts/run-adapted-baseline-smoke-20261126.py'); spec=importlib.util.spec_from_file_location('smoke',s);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
out=Path('/root/autodl-tmp/dag-handoff/runs/common-cost-matrix-v2-20261126');out.mkdir(exist_ok=False)
for n in (1024,2048):
 for b in (1,2,4):
  case=out/f'{n}-{b}';case.mkdir();m.OUT=case
  trace=case/'requests.csv';m.write_csv(trace,[dict(arrived_at=0,num_prefill_tokens=n,num_decode_tokens=128) for _ in range(b)])
  cfg=case/'pd-config.json';m.write_json(cfg,dict(schema_version='1.1',storage_dtype='float16',capacity_bytes_per_shard=5*1024**3,bandwidth_bytes_per_s=255*1024**3/8,latency_s=0,occupies_gpu=True,evidence='synthetic common-cost mechanics diagnostic; profile not frozen',legacy_prefill_billing_extra_token=True))
  for role in ('dag','baseline'):
   wd=m.ROOT if role=='dag' else m.BASE; dest=case/role
   cmd=m.patch(m.pd_command(dest,case/'profiles',trace,cfg),dest,trace)
   for opt,val in [('--random_forrest_execution_time_predictor_config_prediction_max_tokens_per_request','4096'),('--trace_request_generator_config_max_tokens','2176'),('--random_forrest_execution_time_predictor_config_prediction_max_prefill_chunk_size','4096')]:cmd[cmd.index(opt)+1]=val
   if role=='baseline':
    for opt in ('--execution_mode','--dag_pd_config'):
     i=cmd.index(opt);del cmd[i:i+2]
    for opt in ('--metrics_config_write_json_trace','--metrics_config_enable_chrome_trace'):
     if opt in cmd:cmd.remove(opt)
   cmd+=['--replica_config_pd_p2p_comm_bandwidth','255'];code=m.run(wd,cmd,dest)
   with (out/'progress.jsonl').open('a') as f:f.write(json.dumps({'input':n,'requested_batch':b,'role':role,'exit':code})+'\n')
   if code:raise SystemExit(code)
(out/'status.json').write_text(json.dumps({'status':'completed','formal_validation':False,'cases':6,'runs':12,'profile':'candidate v5'},indent=2)+'\n')
