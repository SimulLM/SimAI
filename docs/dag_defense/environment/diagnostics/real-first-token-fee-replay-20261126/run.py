import json,os,pathlib,subprocess
p=pathlib.Path(__file__).parent;repo='/root/autodl-tmp/SimAI-pristine-predictor-repro';tool='/root/autodl-tmp/SimAI-handoff/scripts/dag_defense/batch_first_token_diagnostic/bootstrap.py';old=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/controlled-batches-20261126/simultaneous4/dag/command.json');cmd=json.loads(old.read_text());assert cmd[1:3]==['-m','vidur.main'];cmd[1:3]=[tool];out=p/'dag';out.mkdir()
for flag,val in [('--trace_request_generator_config_trace_file',str(p/'trace.csv')),('--trace_request_generator_config_max_tokens','1032'),('--metrics_config_output_dir',str(out)),('--metrics_config_cache_dir',str(out/'cache')),('--random_forrest_execution_time_predictor_config_simai_dir',str(out))]:
 for i,x in enumerate(cmd):
  if x==flag:cmd[i+1]=val
(out/'command.json').write_text(json.dumps(cmd,indent=2)+'\n');env=dict(os.environ,PYTHONPATH=repo+'/vidur-alibabacloud:'+repo,WANDB_MODE='disabled',PYTHONDONTWRITEBYTECODE='1',BATCH_FIRST_TOKEN_COSTS=str(p/'fee.json'),BATCH_FIRST_TOKEN_TRACE=str(out/'first-token.jsonl'))
with (out/'process.log').open('w') as f:code=subprocess.run(cmd,cwd=repo,env=env,stdout=f,stderr=subprocess.STDOUT).returncode
(out/'exit').write_text(str(code)+'\n');print('DAG exit',code)
