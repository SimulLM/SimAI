import json,os,pathlib,subprocess
p=pathlib.Path(__file__).parent;source=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/real-first-token-2048-replay-20261126');repo='/root/autodl-tmp/SimAI-baseline-kv-ready';tool='/root/autodl-tmp/SimAI-handoff/scripts/dag_defense/batch_first_token_diagnostic/fixed_groups_bootstrap.py';out=p/'baseline';out.mkdir()
cmd=json.loads((source/'original/command.json').read_text());assert cmd[1:3]==['-m','vidur.main'];cmd[1:3]=[tool]
for flag,val in [('--trace_request_generator_config_trace_file',str(source/'trace.csv')),('--metrics_config_output_dir',str(out)),('--metrics_config_cache_dir',str(out/'cache')),('--random_forrest_execution_time_predictor_config_simai_dir',str(out))]:
 for i,x in enumerate(cmd):
  if x==flag:cmd[i+1]=val
cfg={'groups':[{'request_ids':[0],'cost_s':.0011103435},{'request_ids':[1,2],'cost_s':.001115814},{'request_ids':[3],'cost_s':.0011103435}]};(out/'groups.json').write_text(json.dumps(cfg,indent=2)+'\n');(out/'command.json').write_text(json.dumps(cmd,indent=2)+'\n')
env=dict(os.environ,PYTHONPATH=repo+'/vidur-alibabacloud:'+repo,WANDB_MODE='disabled',PYTHONDONTWRITEBYTECODE='1',FIXED_GROUPS_CONFIG=str(out/'groups.json'),FIXED_GROUPS_TRACE=str(out/'first-token.jsonl'))
with (out/'process.log').open('w') as f:code=subprocess.run(cmd,cwd=repo,env=env,stdout=f,stderr=subprocess.STDOUT).returncode
(out/'exit').write_text(str(code)+'\n');print('baseline',code)
