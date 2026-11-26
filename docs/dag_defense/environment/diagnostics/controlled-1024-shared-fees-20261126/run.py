import json,os,pathlib,subprocess,traceback
p=pathlib.Path(__file__).parent;root=pathlib.Path('/root/autodl-tmp/dag-handoff/runs');orig=root/'real-first-token-2048-replay-20261126';repo='/root/autodl-tmp/SimAI-handoff';costs={'1024:1':.000765594,'1024:2':.000912567,'1024:3':.0007040415}
(p/'fee.json').write_text(json.dumps(costs,indent=2)+'\n')
cases=[('one',[0],[[0]]),('two_staggered',[0,.000481173],[[0],[1]]),('two_simultaneous',[0,0],[[0,1]]),('four_simultaneous',[0,0,0,0],[[0],[1,2,3]])]
for name,arrival,groups in cases:
 case=p/name;case.mkdir();(case/'trace.csv').write_text('arrived_at,num_prefill_tokens,num_decode_tokens\n'+''.join(f'{x},1024,128\n' for x in arrival))
 for mode in ('baseline','dag'):
  out=case/mode;out.mkdir();source=orig/('original' if mode=='baseline' else 'dag')/'command.json';cmd=json.loads(source.read_text());work='/root/autodl-tmp/SimAI-baseline-kv-ready' if mode=='baseline' else '/root/autodl-tmp/SimAI-pristine-predictor-repro'
  if mode=='baseline':assert cmd[1:3]==['-m','vidur.main'];cmd[1:3]=[repo+'/scripts/dag_defense/batch_first_token_diagnostic/fixed_groups_resource_bootstrap.py']
  for flag,val in [('--trace_request_generator_config_trace_file',str(case/'trace.csv')),('--trace_request_generator_config_max_tokens','1152'),('--metrics_config_output_dir',str(out)),('--metrics_config_cache_dir',str(out/'cache')),('--random_forrest_execution_time_predictor_config_simai_dir',str(out))]:
   for i,x in enumerate(cmd):
    if x==flag:cmd[i+1]=val
  env=dict(os.environ,PYTHONPATH=work+'/vidur-alibabacloud:'+work,WANDB_MODE='disabled',PYTHONDONTWRITEBYTECODE='1')
  if mode=='baseline':
   cfg={'groups':[{'request_ids':g,'cost_s':costs['1024:'+str(len(g))]} for g in groups]};(out/'groups.json').write_text(json.dumps(cfg,indent=2)+'\n');env.update(FIXED_GROUPS_CONFIG=str(out/'groups.json'),FIXED_GROUPS_TRACE=str(out/'first-token.jsonl'))
  else:env.update(BATCH_FIRST_TOKEN_COSTS=str(p/'fee.json'),BATCH_FIRST_TOKEN_TRACE=str(out/'first-token.jsonl'))
  (out/'command.json').write_text(json.dumps(cmd,indent=2)+'\n')
  with (out/'process.log').open('w') as f:code=subprocess.run(cmd,cwd=work,env=env,stdout=f,stderr=subprocess.STDOUT).returncode
  (out/'exit').write_text(str(code)+'\n');print(name,mode,code,flush=True)
