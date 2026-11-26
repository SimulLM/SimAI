"""Run the separate one-request predictor-adapted baseline diagnostic."""
import json,os,pathlib,subprocess,sys
out=pathlib.Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=False)
src=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/isolated-calibration-first-20261126/adapted_baseline/command.json');cmd=json.loads(src.read_text())
for flag,value in {'--random_forrest_execution_time_predictor_config_simai_dir':str(out),'--metrics_config_output_dir':str(out),'--metrics_config_cache_dir':str(out/'cache')}.items():
 assert cmd.count(flag)==1;cmd[cmd.index(flag)+1]=value
(out/'command.json').write_text(json.dumps(cmd,indent=2)+'\n')
fee=json.loads(pathlib.Path('/root/autodl-tmp/dag-handoff/runs/first-token-task-single-v3-20261126/candidate-config.json').read_text())['consumer_first_token_host_s']
repo='/root/autodl-tmp/SimAI-baseline-first-token';env=dict(os.environ,PYTHONPATH=f'{repo}/vidur-alibabacloud:{repo}',WANDB_MODE='disabled',PYTHONDONTWRITEBYTECODE='1',SIMAI_SERIAL_FIRST_TOKEN_S=str(fee),SIMAI_SERIAL_FIRST_TOKEN_TRACE=str(out/'first-token-events.jsonl'))
(out/'diagnostic-fee.json').write_text(json.dumps({'consumer_first_token_host_s':fee,'status':'serial_candidate_only'},indent=2)+'\n')
with (out/'process.log').open('w') as f:
 try:code=subprocess.run(cmd,cwd=repo,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=900).returncode
 except subprocess.TimeoutExpired:code=124
(out/'exit').write_text(str(code)+'\n');sys.exit(code)
