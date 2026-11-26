import json,pathlib,subprocess,os,hashlib
p=pathlib.Path(__file__).parent;old=pathlib.Path('/root/autodl-tmp/dag-handoff/runs');repo='/root/autodl-tmp/SimAI-handoff';cost=.000912567
(p/'trace.csv').write_text('arrived_at,num_prefill_tokens,num_decode_tokens\n0,1024,128\n0,1024,128\n');(p/'fees.json').write_text(json.dumps({'1024:2':cost},indent=2)+'\n')
for mode in ('baseline','dag'):
 out=p/mode;out.mkdir();source=old/('batch-first-token-fixed-baseline-20261126' if mode=='baseline' else 'batch-first-token-common-predictor-20261126')/'simultaneous2'/'command.json';cmd=json.loads(source.read_text());work='/root/autodl-tmp/SimAI-baseline-kv-ready' if mode=='baseline' else '/root/autodl-tmp/SimAI-pristine-predictor-repro'
 for flag,val in [('--trace_request_generator_config_trace_file',str(p/'trace.csv')),('--trace_request_generator_config_max_tokens','1152'),('--metrics_config_output_dir',str(out)),('--metrics_config_cache_dir',str(out/'cache')),('--random_forrest_execution_time_predictor_config_simai_dir',str(out))]:
  for i,x in enumerate(cmd):
   if x==flag:cmd[i+1]=val
 env=dict(os.environ,PYTHONPATH=work+'/vidur-alibabacloud:'+work,WANDB_MODE='disabled',PYTHONDONTWRITEBYTECODE='1')
 if mode=='baseline':
  (out/'fixed.json').write_text(json.dumps({'request_ids':[0,1],'cost_s':cost})+'\n');env.update(FIXED_FIRST_TOKEN_CONFIG=str(out/'fixed.json'),FIXED_FIRST_TOKEN_TRACE=str(out/'first-token.jsonl'))
 else:env.update(BATCH_FIRST_TOKEN_COSTS=str(p/'fees.json'),BATCH_FIRST_TOKEN_TRACE=str(out/'first-token.jsonl'))
 (out/'command.json').write_text(json.dumps(cmd,indent=2)+'\n')
 with (out/'process.log').open('w') as f:code=subprocess.run(cmd,cwd=work,env=env,stdout=f,stderr=subprocess.STDOUT).returncode
 (out/'exit').write_text(str(code)+'\n');print(mode,code,flush=True)
