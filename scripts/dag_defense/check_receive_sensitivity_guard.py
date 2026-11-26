"""Ensure the baseline receiver override refuses a multi-request trace."""
import json,os,pathlib,subprocess,sys
out=pathlib.Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=False);root=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/receive-sensitivity-single-20261126');cmd=json.loads((root/'baseline/command.json').read_text())
changes={'--trace_request_generator_config_trace_file':'/root/autodl-tmp/dag-handoff/runs/pd-pull-calibration-replay-20261126/serial-0/trace.csv','--random_forrest_execution_time_predictor_config_simai_dir':str(out),'--metrics_config_output_dir':str(out),'--metrics_config_cache_dir':str(out/'cache')}
for k,v in changes.items():assert cmd.count(k)==1;cmd[cmd.index(k)+1]=v
repo='/root/autodl-tmp/SimAI-baseline-first-token';env=dict(os.environ,PYTHONPATH=f'{repo}/vidur-alibabacloud:{repo}',WANDB_MODE='disabled',SIMAI_SERIAL_RECV_INTERCEPT_S='0.0045052672',SIMAI_SERIAL_RECV_PER_TOKEN_S='0.000015727422116815475');env.pop('SIMAI_SERIAL_FIRST_TOKEN_S',None)
with (out/'process.log').open('w') as f:r=subprocess.run(cmd,cwd=repo,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=900)
passed=r.returncode!=0 and 'first-token diagnostic only supports one request' in (out/'process.log').read_text();(out/'status.json').write_text(json.dumps({'guard_pass':passed,'exit_code':r.returncode},indent=2)+'\n');sys.exit(0 if passed else 1)
