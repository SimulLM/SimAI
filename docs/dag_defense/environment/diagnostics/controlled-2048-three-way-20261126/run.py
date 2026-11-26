import json,os,pathlib,subprocess
p=pathlib.Path(__file__).parent;old=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/real-first-token-2048-replay-20261126/original/command.json');cases=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/controlled-2048-shared-fees-20261126');repo='/root/autodl-tmp/SimAI-pristine-baseline'
for name in ('one','two_staggered','two_simultaneous','four_simultaneous'):
 out=p/name;out.mkdir();cmd=json.loads(old.read_text());assert cmd[1:3]==['-m','vidur.main']
 for flag,val in [('--trace_request_generator_config_trace_file',str(cases/name/'trace.csv')),('--trace_request_generator_config_max_tokens','2176'),('--metrics_config_output_dir',str(out)),('--metrics_config_cache_dir',str(out/'cache')),('--random_forrest_execution_time_predictor_config_simai_dir',str(out))]:
  for i,x in enumerate(cmd):
   if x==flag:cmd[i+1]=val
 (out/'command.json').write_text(json.dumps(cmd,indent=2)+'\n');env=dict(os.environ,PYTHONPATH=repo+'/vidur-alibabacloud:'+repo,WANDB_MODE='disabled',PYTHONDONTWRITEBYTECODE='1')
 with (out/'process.log').open('w') as f:code=subprocess.run(cmd,cwd=repo,env=env,stdout=f,stderr=subprocess.STDOUT).returncode
 (out/'exit').write_text(str(code)+'\n');print(name,code,flush=True)
