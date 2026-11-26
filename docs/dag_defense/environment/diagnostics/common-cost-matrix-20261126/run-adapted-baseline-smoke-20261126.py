import json,os,subprocess,sys
from pathlib import Path
ROOT=Path('/root/autodl-tmp/SimAI-handoff');OUT=Path('/root/autodl-tmp/dag-handoff/runs/adapted-baseline-smoke-20261126');PROFILE=Path('/root/autodl-tmp/dag-handoff/runs/hardware-vidur-profile-v5-20261126');BASE=Path('/root/autodl-tmp/SimAI-baseline')
sys.path[:0]=[str(ROOT),str(ROOT/'vidur-alibabacloud')]
from scripts.dag_phase4.main import write_csv,write_json
from scripts.dag_phase6.main import pd_command

def patch(cmd,out,trace):
 replacements={'--replica_config_model_name':'NousResearch/Llama-2-7b-hf','--replica_config_device':'h800','--random_forrest_execution_time_predictor_config_compute_input_file':str(PROFILE/'compute.csv'),'--random_forrest_execution_time_predictor_config_attention_input_file':str(PROFILE/'attention.csv'),'--random_forrest_execution_time_predictor_config_cpu_overhead_input_file':str(PROFILE/'cpu.csv'),'--random_forrest_execution_time_predictor_config_send_recv_input_file':str(PROFILE/'network.csv'),'--random_forrest_execution_time_predictor_config_all_reduce_input_file':str(PROFILE/'network.csv'),'--random_forrest_execution_time_predictor_config_prediction_max_tokens_per_request':'2048','--random_forrest_execution_time_predictor_config_prediction_max_prefill_chunk_size':'2048','--random_forrest_execution_time_predictor_config_prediction_max_batch_size':'4','--metrics_config_output_dir':str(out),'--metrics_config_cache_dir':str(out/'cache'),'--trace_request_generator_config_trace_file':str(trace),'--trace_request_generator_config_max_tokens':'576'}
 for flag,val in replacements.items():
  if flag in cmd:cmd[cmd.index(flag)+1]=val
  else:cmd.extend([flag,val])
 cmd += ['--no-random_forrest_execution_time_predictor_config_skip_cpu_overhead_modeling']
 # model profile uses real H800 field but predictor reads model config, not device label.
 return cmd

def run(cwd,cmd,out):
 out.mkdir(parents=True,exist_ok=False);env=dict(os.environ,PYTHONPATH=f'{cwd}/vidur-alibabacloud:{cwd}',WANDB_MODE='disabled',PYTHONDONTWRITEBYTECODE='1')
 (out/'command.json').write_text(json.dumps(cmd,indent=2)+'\n')
 with (out/'process.log').open('w') as f:r=subprocess.run(cmd,cwd=cwd,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=300)
 (out/'exit-code').write_text(str(r.returncode)+'\n');print(out,'exit',r.returncode);return r.returncode

def main():
 if OUT.exists():raise FileExistsError(OUT)
 OUT.mkdir(parents=True);profiles=OUT/'profiles';profiles.mkdir();trace=OUT/'requests.csv';write_csv(trace,[dict(arrived_at=0,num_prefill_tokens=512,num_decode_tokens=64)])
 config=OUT/'pd-config.json';write_json(config,dict(schema_version='1.1',storage_dtype='float16',capacity_bytes_per_shard=5*1024**3,bandwidth_bytes_per_s=255*1024**3/8,latency_s=0,occupies_gpu=True,evidence='provisional hardware profile smoke; not frozen',legacy_prefill_billing_extra_token=True))
 # Build DAG command in a disposable local fixture, then patch all shared predictor paths.
 dag=OUT/'dag';cmd=patch(pd_command(dag,profiles,trace,config),dag,trace);cmd += ['--replica_config_pd_p2p_comm_bandwidth','255'];run(ROOT,cmd,dag)
 # Baseline from the pinned independent checkout, with same profile and trace.
 old=OUT/'baseline';cmd=patch(pd_command(old,profiles,trace,config),old,trace)
 for option in ('--execution_mode','--dag_pd_config'):
  i=cmd.index(option);del cmd[i:i+2]
 for flag in ('--metrics_config_write_json_trace','--metrics_config_enable_chrome_trace'): 
  if flag in cmd:cmd.remove(flag)
 cmd += ['--replica_config_pd_p2p_comm_bandwidth','255'];run(BASE,cmd,old)
 (OUT/'status.json').write_text(json.dumps({'status':'adapted_baseline_diagnostic_only','formal_validation':False,'profile':str(PROFILE),'dag_exit':int((dag/'exit-code').read_text()),'baseline_exit':int((old/'exit-code').read_text())},indent=2)+'\n')
if __name__=='__main__':main()
