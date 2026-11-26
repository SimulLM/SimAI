import json,os,pathlib,subprocess
p=pathlib.Path(__file__).parent;old=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/dynamic-calibration-512-20261126/concurrent-0/dag');repo='/root/autodl-tmp/SimAI-pristine-predictor-repro';cmd=json.loads((old/'command.json').read_text());source=[pathlib.Path(cmd[i+1]) for i,x in enumerate(cmd) if x=='--dag_pd_config'];assert source and len({x.read_bytes() for x in source})==1
cfg=json.loads(source[0].read_text());assert cfg['occupies_gpu'] is True;cfg['occupies_gpu']=False;cfg['evidence']='CPU sensitivity only; no claim about physical overlap';(p/'pd-config.json').write_text(json.dumps(cfg,indent=2)+'\n')
for flag,val in [('--dag_pd_config',str(p/'pd-config.json')),('--metrics_config_output_dir',str(p)),('--metrics_config_cache_dir',str(p/'cache')),('--random_forrest_execution_time_predictor_config_simai_dir',str(p))]:
 for i,x in enumerate(cmd):
  if x==flag:cmd[i+1]=val
fee='/root/autodl-tmp/dag-handoff/runs/dynamic-calibration-512-20261126/fee.json';env=dict(os.environ,PYTHONPATH=repo+'/vidur-alibabacloud:'+repo,WANDB_MODE='disabled',PYTHONDONTWRITEBYTECODE='1',BATCH_FIRST_TOKEN_COSTS=fee,BATCH_FIRST_TOKEN_TRACE=str(p/'first-token.jsonl'))
(p/'command.json').write_text(json.dumps(cmd,indent=2)+'\n')
with (p/'process.log').open('w') as f:code=subprocess.run(cmd,cwd=repo,env=env,stdout=f,stderr=subprocess.STDOUT).returncode
(p/'exit').write_text(str(code)+'\n');print('exit',code,flush=True)
