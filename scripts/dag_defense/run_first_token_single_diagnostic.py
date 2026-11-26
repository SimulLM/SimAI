"""Re-run isolated candidate DAG with a separate measured first-token task."""
import json,os,pathlib,subprocess,sys
out=pathlib.Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=False)
base=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/isolated-calibration-first-20261126/dag/command.json');cmd=json.loads(base.read_text())
config=pathlib.Path(cmd[cmd.index('--dag_pd_config')+1]);data=json.loads(config.read_text());sample=json.loads(pathlib.Path('/root/autodl-tmp/dag-handoff/runs/pd-postkv-512-audit-20261126/summary.json').read_text())
data.update(schema_version='1.5',decode_dispatch_delay_s=0.0,pull_wait_source_batch=False,consumer_first_token_host_s=sample['statistics']['host_post_sync_ms']['median_ms']/1000,evidence='instrumented 512-token serial post-KV host interval; sensitivity only')
cfg=out/'candidate-config.json';cfg.write_text(json.dumps(data,indent=2)+'\n')
changes={'--random_forrest_execution_time_predictor_config_simai_dir':str(out),'--metrics_config_output_dir':str(out),'--metrics_config_cache_dir':str(out/'cache')}
for key,value in changes.items():assert cmd.count(key)==1;cmd[cmd.index(key)+1]=value
for i,v in enumerate(cmd):
 if v=='--dag_pd_config':cmd[i+1]=str(cfg)
(out/'command.json').write_text(json.dumps(cmd,indent=2)+'\n')
repo='/root/autodl-tmp/SimAI-handoff';env=dict(os.environ,PYTHONPATH=f'{repo}/vidur-alibabacloud:{repo}',WANDB_MODE='disabled',PYTHONDONTWRITEBYTECODE='1')
with (out/'process.log').open('w') as f:
 try:code=subprocess.run(cmd,cwd=repo,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=900).returncode
 except subprocess.TimeoutExpired:code=124
(out/'exit').write_text(str(code)+'\n');sys.exit(code)
