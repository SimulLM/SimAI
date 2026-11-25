import csv,json,os,subprocess,sys
from pathlib import Path
ROOT=Path('/root/autodl-tmp/SimAI-handoff'); BASE=Path('/root/autodl-tmp/SimAI-baseline')
OUT=Path('/root/autodl-tmp/dag-handoff/runs/arrival-replay-v2-20261126')
PROFILE=Path('/root/autodl-tmp/dag-handoff/runs/hardware-vidur-profile-v3-20261126')
CAL=Path('/root/autodl-tmp/dag-handoff/runs/calibration-merged-20261126')
REQ=Path('/root/autodl-tmp/dag-handoff/runs/calibration-merged-20261126')
EVENTS=Path('/root/autodl-tmp/dag-handoff/runs/calibration-server-20261126')
sys.path[:0]=[str(ROOT),str(ROOT/'vidur-alibabacloud')]
from scripts.dag_phase4.main import write_csv,write_json
from scripts.dag_phase6.main import pd_command

def build_trace():
 req=json.loads((REQ/'requests.json').read_text())
 events={}
 for line in (EVENTS/'router-events.jsonl').read_text().splitlines():
  x=json.loads(line); events.setdefault(x['request_id'],{})[x['event']]=x['timestamp_ns']
 rows=[x for x in req if x.get('repeat')==0 and x.get('mode')=='serial']
 rows.sort(key=lambda x: events[x['router_id']]['server_arrival'])
 first=events[rows[0]['router_id']]['server_arrival']
 out=[]
 for x in rows:
  e=events[x['router_id']]
  out.append({'arrived_at':(e['server_arrival']-first)/1e9,'num_prefill_tokens':x['usage']['prompt_tokens'],'num_decode_tokens':x['usage']['completion_tokens']})
 return out

def patch(cmd,out,trace,pd):
 repl={'--replica_config_model_name':'NousResearch/Llama-2-7b-hf','--replica_config_device':'h800','--random_forrest_execution_time_predictor_config_compute_input_file':str(PROFILE/'compute.csv'),'--random_forrest_execution_time_predictor_config_attention_input_file':str(PROFILE/'attention.csv'),'--random_forrest_execution_time_predictor_config_cpu_overhead_input_file':str(PROFILE/'cpu.csv'),'--random_forrest_execution_time_predictor_config_send_recv_input_file':str(PROFILE/'network.csv'),'--random_forrest_execution_time_predictor_config_all_reduce_input_file':str(PROFILE/'network.csv'),'--random_forrest_execution_time_predictor_config_prediction_max_tokens_per_request':'4096','--random_forrest_execution_time_predictor_config_prediction_max_prefill_chunk_size':'2048','--random_forrest_execution_time_predictor_config_prediction_max_batch_size':'4','--metrics_config_output_dir':str(out),'--metrics_config_cache_dir':str(out/'cache'),'--trace_request_generator_config_trace_file':str(trace),'--trace_request_generator_config_max_tokens':'576'}
 for flag,val in repl.items():
  if flag in cmd: cmd[cmd.index(flag)+1]=val
  else: cmd += [flag,val]
 cmd += ['--no-random_forrest_execution_time_predictor_config_skip_cpu_overhead_modeling']
 if pd: cmd += ['--replica_config_pd_p2p_comm_bandwidth','255','--dag_pd_config',str(OUT/'pd-config.json')]
 return cmd

def run(cwd,cmd,out):
 out.mkdir(parents=True,exist_ok=False); env=dict(os.environ,PYTHONPATH=f'{cwd}/vidur-alibabacloud:{cwd}',WANDB_MODE='disabled',PYTHONDONTWRITEBYTECODE='1')
 (out/'command.json').write_text(json.dumps(cmd,indent=2)+'\n')
 r=subprocess.run(cmd,cwd=cwd,env=env,stdout=(out/'process.log').open('w'),stderr=subprocess.STDOUT,timeout=900)
 (out/'process-returncode').write_text(str(r.returncode)+'\n')
 return r.returncode

def main():
 OUT.mkdir(parents=True,exist_ok=False)
 trace=OUT/'requests.csv'; rows=build_trace(); write_csv(trace,rows)
 cfg=OUT/'pd-config.json'; write_json(cfg,dict(schema_version='1.1',storage_dtype='float16',capacity_bytes_per_shard=5*1024**3,bandwidth_bytes_per_s=255*1024**3/8,latency_s=0,occupies_gpu=True,evidence='v3 candidate arrival replay; not frozen',legacy_prefill_billing_extra_token=True))
 dag=OUT/'dag'; dcmd=patch(pd_command(dag,OUT/'profiles',trace,cfg),dag,trace,True); dcode=run(ROOT,dcmd,dag)
 old=OUT/'baseline'; bcmd=patch(pd_command(old,OUT/'profiles',trace,cfg),old,trace,False)
 for opt in ('--execution_mode','--dag_pd_config'):
  if opt in bcmd:
   i=bcmd.index(opt); del bcmd[i:i+2]
 for flag in ('--metrics_config_write_json_trace','--metrics_config_enable_chrome_trace'):
  if flag in bcmd: bcmd.remove(flag)
 bcode=run(BASE,bcmd,old)
 write_json(OUT/'status.json',dict(status='arrival_replay_completed',request_count=len(rows),source='calibration server_arrival CLOCK_MONOTONIC',dag_returncode=dcode,baseline_returncode=bcode,formal_validation=False))
if __name__=='__main__': main()
