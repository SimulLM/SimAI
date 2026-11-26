import json,os,pathlib,subprocess
root=pathlib.Path(__file__).parent;source=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/controlled-batches-20261126');repo='/root/autodl-tmp/SimAI-baseline-kv-ready';tool='/root/autodl-tmp/SimAI-handoff/scripts/dag_defense/batch_first_token_diagnostic/baseline_bootstrap.py'
for name,count,cost in [('simultaneous2',2,.0015),('simultaneous4',4,.002)]:
 out=root/name;out.mkdir();cmd=json.loads((source/name/'corrected/command.json').read_text());assert cmd[1:3]==['-m','vidur.main'];cmd[1:3]=[tool]
 for flag,val in [('--trace_request_generator_config_trace_file',str(source/name/'trace.csv')),('--metrics_config_output_dir',str(out)),('--metrics_config_cache_dir',str(out/'cache')),('--random_forrest_execution_time_predictor_config_simai_dir',str(out))]:
  for i,x in enumerate(cmd):
   if x==flag:cmd[i+1]=val
 cfg=out/'fixed.json';cfg.write_text(json.dumps({'request_ids':list(range(count)),'cost_s':cost},indent=2)+'\n');(out/'command.json').write_text(json.dumps(cmd,indent=2)+'\n')
 env=dict(os.environ,PYTHONPATH=repo+'/vidur-alibabacloud:'+repo,WANDB_MODE='disabled',PYTHONDONTWRITEBYTECODE='1',FIXED_FIRST_TOKEN_CONFIG=str(cfg),FIXED_FIRST_TOKEN_TRACE=str(out/'first-token.jsonl'))
 with (out/'process.log').open('w') as f:code=subprocess.run(cmd,cwd=repo,env=env,stdout=f,stderr=subprocess.STDOUT).returncode
 (out/'exit').write_text(str(code)+'\n');print(name,code,flush=True)
