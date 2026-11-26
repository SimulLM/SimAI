"""Exercise the actual CLI and require rejection of a 32-request trace."""
import json,os,pathlib,subprocess,sys
out=pathlib.Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=False)
cmd=json.loads(pathlib.Path('/root/autodl-tmp/dag-handoff/runs/baseline-first-token-single-v2-20261126/command.json').read_text())
for flag,value in {'--trace_request_generator_config_trace_file':'/root/autodl-tmp/dag-handoff/runs/pd-pull-calibration-replay-20261126/serial-0/trace.csv','--random_forrest_execution_time_predictor_config_simai_dir':str(out),'--metrics_config_output_dir':str(out),'--metrics_config_cache_dir':str(out/'cache')}.items():
 assert cmd.count(flag)==1;cmd[cmd.index(flag)+1]=value
repo='/root/autodl-tmp/SimAI-baseline-first-token';env=dict(os.environ,PYTHONPATH=f'{repo}/vidur-alibabacloud:{repo}',WANDB_MODE='disabled',PYTHONDONTWRITEBYTECODE='1',SIMAI_SERIAL_FIRST_TOKEN_S='0.000875779',SIMAI_SERIAL_FIRST_TOKEN_TRACE=str(out/'events.jsonl'))
with (out/'process.log').open('w') as f:
 try:code=subprocess.run(cmd,cwd=repo,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=900).returncode
 except subprocess.TimeoutExpired:code=124
log=(out/'process.log').read_text();passed=code not in (0,124) and 'first-token diagnostic only supports one request' in log
(out/'result.json').write_text(json.dumps({'status':'guard_pass' if passed else 'guard_fail','exit_code':code,'expected':'reject more than one request'},indent=2)+'\n');sys.exit(0 if passed else 1)
