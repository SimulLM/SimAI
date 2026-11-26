import os,subprocess,json,pathlib,sys
out=pathlib.Path(__file__).parent;old=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/whole-forward-replay-20261126');repo='/root/autodl-tmp/SimAI-handoff';adapt='/root/autodl-tmp/SimAI-baseline-first-token';boot=repo+'/scripts/dag_defense/forward_diagnostic/bootstrap.py';root=repo+'/docs/dag_defense/environment/diagnostics';pref=root+'/pd-eager-profile-20261126/candidate/forward-cost.csv';dec=root+'/forward-coverage-refresh-20261126/strict-forward-context-bins.csv'
for mode in ('baseline','dag'):
 dest=out/mode;dest.mkdir(exist_ok=False);oldcmd=json.loads((old/mode/'command.json').read_text());cmd=oldcmd[:];cmd[1]=boot
 for flag,val in [('--trace_request_generator_config_trace_file',str(out/'trace.csv')),('--trace_request_generator_config_max_tokens','1152'),('--random_forrest_execution_time_predictor_config_simai_dir',str(dest)),('--metrics_config_output_dir',str(dest)),('--metrics_config_cache_dir',str(dest/'cache'))]:
  if flag in cmd:cmd[cmd.index(flag)+1]=val
 env=dict(os.environ,PYTHONPATH=f'{adapt if mode=="baseline" else repo}/vidur-alibabacloud:{adapt if mode=="baseline" else repo}:{repo}',WANDB_MODE='disabled',PYTHONDONTWRITEBYTECODE='1',FORWARD_DIAG_MODE=mode,FORWARD_DIAG_TRACE=str(dest/'forward.jsonl'),FORWARD_PREFILL_CSV=pref,FORWARD_DECODE_CSV=dec)
 for key in ('SIMAI_SERIAL_FIRST_TOKEN_S','SIMAI_SERIAL_RECV_INTERCEPT_S','SIMAI_SERIAL_RECV_PER_TOKEN_S','SIMAI_SERIAL_FIRST_TOKEN_TRACE'):env.pop(key,None)
 (dest/'command.json').write_text(json.dumps(cmd,indent=2)+'\n')
 with (dest/'process.log').open('w') as f:code=subprocess.run(cmd,cwd=adapt if mode=='baseline' else repo,env=env,stdout=f,stderr=subprocess.STDOUT).returncode
 (dest/'exit').write_text(str(code)+'\n');print(mode,code,flush=True)
 if code:sys.exit(code)
