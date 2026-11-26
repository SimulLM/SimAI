"""Run an isolated same-fee serial sensitivity with independent interval fit."""
import concurrent.futures,json,os,pathlib,subprocess,sys
out=pathlib.Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=False)
source=pathlib.Path('/root/autodl-tmp/dag-handoff/runs');dag=source/'first-token-task-single-v3-20261126';base=source/'baseline-first-token-single-v2-20261126';fit=json.loads((source/'receive-install-fit-20261126/summary.json').read_text());intercept=fit['split_fit_intercept_ms']/1000;slope=fit['split_fit_ms_per_token']/1000
cfg=json.loads((dag/'candidate-config.json').read_text());cfg.update(legacy_prefill_billing_extra_token=False,latency_s=intercept,bandwidth_bytes_per_s=524288/slope,evidence='separate intrusive serial receive/install sensitivity; not frozen');config=out/'candidate-config.json';config.write_text(json.dumps(cfg,indent=2)+'\n')
(out/'fit-coefficients.json').write_text(json.dumps({'intercept_s':intercept,'per_input_token_s':slope,'source':'independent split-fit; synchronized serial diagnostic','formal_validation':False},indent=2)+'\n')
def run(name,cmd_source,repo):
 dest=out/name;dest.mkdir();cmd=json.loads((cmd_source/'command.json').read_text());changes={'--random_forrest_execution_time_predictor_config_simai_dir':str(dest),'--metrics_config_output_dir':str(dest),'--metrics_config_cache_dir':str(dest/'cache')}
 for key,value in changes.items():assert cmd.count(key)==1;cmd[cmd.index(key)+1]=value
 if name=='dag':
  for i,x in enumerate(cmd):
   if x=='--dag_pd_config':cmd[i+1]=str(config)
 env=dict(os.environ,PYTHONPATH=f'{repo}/vidur-alibabacloud:{repo}',WANDB_MODE='disabled',PYTHONDONTWRITEBYTECODE='1')
 if name=='baseline':env.update(SIMAI_SERIAL_FIRST_TOKEN_S=str(cfg['consumer_first_token_host_s']),SIMAI_SERIAL_FIRST_TOKEN_TRACE=str(dest/'first-token-events.jsonl'),SIMAI_SERIAL_RECV_INTERCEPT_S=str(intercept),SIMAI_SERIAL_RECV_PER_TOKEN_S=str(slope))
 (dest/'command.json').write_text(json.dumps(cmd,indent=2)+'\n')
 with (dest/'process.log').open('w') as log:
  try:code=subprocess.run(cmd,cwd=repo,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=900).returncode
  except subprocess.TimeoutExpired:code=124
 (dest/'exit').write_text(str(code)+'\n');return {'name':name,'exit':code}
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
 jobs=[pool.submit(run,'dag',dag,'/root/autodl-tmp/SimAI-handoff'),pool.submit(run,'baseline',base,'/root/autodl-tmp/SimAI-baseline-first-token')];results=[x.result() for x in jobs]
(out/'status.json').write_text(json.dumps({'results':results,'formal_validation':False},indent=2)+'\n');sys.exit(0 if all(x['exit']==0 for x in results) else 1)
