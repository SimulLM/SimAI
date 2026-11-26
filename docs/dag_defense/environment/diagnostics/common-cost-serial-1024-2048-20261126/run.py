import concurrent.futures,json,os,pathlib,subprocess
base=pathlib.Path(__file__).parent;src=pathlib.Path('/root/autodl-tmp/dag-handoff/runs');summary=json.loads(pathlib.Path('/root/autodl-tmp/SimAI-handoff/docs/dag_defense/environment/diagnostics/paired-receive-first-cost-20261126/summary.json').read_text());fit=json.loads((src/'receive-install-fit-20261126/summary.json').read_text());slope=fit['split_fit_ms_per_token']/1000
cases={r['input_tokens']:r for r in summary['rows']}
def run(length,mode):
 row=cases[length];out=base/str(length);out.mkdir(exist_ok=True);dest=out/mode;dest.mkdir();trace=out/'trace.csv'
 if not trace.exists():trace.write_text(f'arrived_at,num_prefill_tokens,num_decode_tokens\n0,{length},128\n')
 receive=row['receive_ms']['median']/1000;first=row['post_ms']['median']/1000;intercept=receive-length*slope
 cfg=json.loads((src/'first-token-task-single-v3-20261126/candidate-config.json').read_text());cfg.update(consumer_first_token_host_s=first,legacy_prefill_billing_extra_token=False,latency_s=intercept,bandwidth_bytes_per_s=524288/slope,evidence='serial point encoding only; no slope extrapolation; intrusive sync')
 config=dest/'candidate-config.json';config.write_text(json.dumps(cfg,indent=2)+'\n')
 old=src/('first-token-task-single-v3-20261126' if mode=='dag' else 'baseline-first-token-single-v2-20261126');cmd=json.loads((old/'command.json').read_text());repo='/root/autodl-tmp/'+('SimAI-handoff' if mode=='dag' else 'SimAI-baseline-first-token')
 for flag,val in [('--trace_request_generator_config_trace_file',str(trace)),('--trace_request_generator_config_max_tokens',str(length+128)),('--metrics_config_output_dir',str(dest)),('--metrics_config_cache_dir',str(dest/'cache')),('--random_forrest_execution_time_predictor_config_simai_dir',str(dest)),('--random_forrest_execution_time_predictor_config_prediction_max_prefill_chunk_size','4096')]:
  for i,x in enumerate(cmd):
   if x==flag:cmd[i+1]=val
 if mode=='dag':
  for i,x in enumerate(cmd):
   if x=='--dag_pd_config':cmd[i+1]=str(config)
 env=dict(os.environ,PYTHONPATH=repo+'/vidur-alibabacloud:'+repo,WANDB_MODE='disabled',PYTHONDONTWRITEBYTECODE='1')
 if mode=='baseline':env.update(SIMAI_SERIAL_FIRST_TOKEN_S=str(first),SIMAI_SERIAL_FIRST_TOKEN_TRACE=str(dest/'first-token-events.jsonl'),SIMAI_SERIAL_RECV_INTERCEPT_S=str(intercept),SIMAI_SERIAL_RECV_PER_TOKEN_S=str(slope))
 (dest/'command.json').write_text(json.dumps(cmd,indent=2)+'\n');(dest/'cost-encoding.json').write_text(json.dumps({'receive_s':receive,'first_s':first,'intercept_s':intercept,'slope_s_per_token':slope,'warning':'point encoding only; no extrapolation'},indent=2)+'\n')
 with (dest/'process.log').open('w') as f:r=subprocess.run(cmd,cwd=repo,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=900)
 (dest/'exit').write_text(str(r.returncode)+'\n');print(length,mode,r.returncode,flush=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
 futures=[pool.submit(run,n,m) for n in (1024,2048) for m in ('dag','baseline')]
 for f in futures:f.result()
