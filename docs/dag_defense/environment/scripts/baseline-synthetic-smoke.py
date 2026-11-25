import json,os,subprocess
from pathlib import Path
root=Path('/root/autodl-tmp/SimAI-baseline'); runs=Path('/root/autodl-tmp/dag-handoff/runs/simulator-env-20261126'); out=runs/'baseline-synthetic-smoke-no-json'; out.mkdir(exist_ok=False)
cmd=json.loads((runs/'dag-synthetic-smoke/single/cli/command.json').read_text())
for option in ('--execution_mode','--dag_pd_config'):
 i=cmd.index(option); del cmd[i:i+2]
for flag in ('--metrics_config_write_json_trace','--metrics_config_enable_chrome_trace'): cmd.remove(flag)
for option,path in [('--random_forrest_execution_time_predictor_config_simai_dir',out),('--metrics_config_output_dir',out),('--metrics_config_cache_dir',out/'cache')]: cmd[cmd.index(option)+1]=str(path)
(out/'command.json').write_text(json.dumps(cmd,indent=2)+'\n')
env=dict(os.environ,PYTHONPATH=f'{root}/vidur-alibabacloud:{root}',WANDB_MODE='disabled',PYTHONDONTWRITEBYTECODE='1')
with (out/'process.log').open('w') as log: proc=subprocess.run(cmd,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=180)
(out/'exit-code').write_text(str(proc.returncode)+'\n')
print('baseline process exit',proc.returncode)
if proc.returncode: raise SystemExit(proc.returncode)
log=(out/'process.log').read_text(); files=list(out.glob('*/plots/request_e2e_time.csv')); assert 'Simulation ended at:' in log and 'Traceback' not in log and len(files)==1 and len(files[0].read_text().splitlines())==2, 'simulation output incomplete'; print('PASS: one request metric saved without shutdown error')
