import json,os,pathlib,subprocess
p=pathlib.Path(__file__).parent;old=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/pristine-real-arrival-20261126');src='/root/autodl-tmp/SimAI-handoff/scripts/dag_defense/batch_first_token_diagnostic/';fees={'512:1':.000875779,'512:2':.000833501};(p/'fee.json').write_text(json.dumps(fees,indent=2)+'\n')
for case in ('serial-0','concurrent-0'):
 for mode in ('baseline','dag'):
  original=old/case/('baseline' if mode=='baseline' else 'dag');out=p/case/mode;out.mkdir(parents=True);cmd=json.loads((original/'command.json').read_text());assert cmd[1:3]==['-m','vidur.main'];cmd[1:3]=[src+('dynamic_groups_bootstrap.py' if mode=='baseline' else 'bootstrap.py')]
  for flag,val in [('--metrics_config_output_dir',str(out)),('--metrics_config_cache_dir',str(out/'cache')),('--random_forrest_execution_time_predictor_config_simai_dir',str(out))]:
   for i,x in enumerate(cmd):
    if x==flag:cmd[i+1]=val
  repo='/root/autodl-tmp/SimAI-baseline-kv-ready' if mode=='baseline' else '/root/autodl-tmp/SimAI-pristine-predictor-repro';env=dict(os.environ,PYTHONPATH=repo+'/vidur-alibabacloud:'+repo,WANDB_MODE='disabled',PYTHONDONTWRITEBYTECODE='1',BATCH_FIRST_TOKEN_COSTS=str(p/'fee.json'),BATCH_FIRST_TOKEN_TRACE=str(out/'first-token.jsonl'))
  (out/'command.json').write_text(json.dumps(cmd,indent=2)+'\n')
  with (out/'process.log').open('w') as f:code=subprocess.run(cmd,cwd=repo,env=env,stdout=f,stderr=subprocess.STDOUT).returncode
  (out/'exit').write_text(str(code)+'\n');print(case,mode,code,flush=True)
