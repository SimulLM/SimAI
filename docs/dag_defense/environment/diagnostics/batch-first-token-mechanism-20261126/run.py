import json,pathlib,subprocess,os
p=pathlib.Path(__file__).parent;old=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/controlled-batches-20261126');repo='/root/autodl-tmp/SimAI-handoff';boot=repo+'/scripts/dag_defense/batch_first_token_diagnostic/bootstrap.py'
for case in ('simultaneous2','simultaneous4'):
 out=p/case;out.mkdir();cmd=json.loads((old/case/'dag/command.json').read_text());cmd[1:3]=[boot]
 for flag,value in [('--trace_request_generator_config_trace_file',str(old/case/'trace.csv')),('--metrics_config_output_dir',str(out)),('--metrics_config_cache_dir',str(out/'cache')),('--random_forrest_execution_time_predictor_config_simai_dir',str(out))]:
  for i,x in enumerate(cmd):
   if x==flag:cmd[i+1]=value
 env=dict(os.environ,PYTHONPATH=repo+'/vidur-alibabacloud:'+repo,WANDB_MODE='disabled',PYTHONDONTWRITEBYTECODE='1',BATCH_FIRST_TOKEN_COSTS=str(p/'synthetic-fees.json'),BATCH_FIRST_TOKEN_TRACE=str(out/'first-token.jsonl'))
 (out/'command.json').write_text(json.dumps(cmd,indent=2)+'\n')
 with (out/'process.log').open('w') as f:code=subprocess.run(cmd,cwd=repo,env=env,stdout=f,stderr=subprocess.STDOUT).returncode
 (out/'exit').write_text(str(code)+'\n');print(case,code,flush=True)
