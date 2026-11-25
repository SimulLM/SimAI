"""Compare pinned baseline and DAG PD fees with synthetic profiles, not accuracy."""
import argparse,csv,json,math,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'vidur-alibabacloud')]
from scripts.dag_phase4.main import synthetic_profiles,write_csv,write_json
from scripts.dag_phase6.main import pd_command

def execute(cmd,cwd,out):
 out.mkdir(parents=True,exist_ok=False);(out/'command.json').write_text(json.dumps(cmd,indent=2)+'\n')
 env=dict(os.environ,PYTHONPATH=f'{cwd}/vidur-alibabacloud:{cwd}',WANDB_MODE='disabled',PYTHONDONTWRITEBYTECODE='1')
 with (out/'process.log').open('w') as f:result=subprocess.run(cmd,cwd=cwd,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=120)
 (out/'exit-code').write_text(str(result.returncode)+'\n');log=(out/'process.log').read_text()
 if result.returncode or 'Traceback' in log or 'Exception ignored' in log:raise RuntimeError(f'simulation failed: {out}')

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--baseline',type=Path,required=True);p.add_argument('--bandwidth-gibits',type=int,default=800);a=p.parse_args();assert a.bandwidth_gibits>0;out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);base=a.baseline.resolve();profiles=out/'synthetic-profiles';synthetic_profiles(profiles)
 bw=a.bandwidth_gibits*1024**3/8;results=[]
 for n in (8,16,32):
  case=out/f'n{n}';case.mkdir();trace=case/'requests.csv';write_csv(trace,[dict(arrived_at=0,num_prefill_tokens=n,num_decode_tokens=4)])
  config=case/'pd-config.json';write_json(config,dict(schema_version='1.1',storage_dtype='float16',capacity_bytes_per_shard=134217728,bandwidth_bytes_per_s=bw,latency_s=0,occupies_gpu=True,evidence='synthetic parity test only',legacy_prefill_billing_extra_token=True))
  dag=case/'dag';cmd=pd_command(dag,profiles,trace,config);cmd += ['--replica_config_pd_p2p_comm_bandwidth',str(a.bandwidth_gibits)];cmd[cmd.index('--random_forrest_execution_time_predictor_config_prediction_max_prefill_chunk_size')+1]='64';execute(cmd,ROOT,dag)
  old=case/'baseline';cmd=pd_command(old,profiles,trace,config);cmd += ['--replica_config_pd_p2p_comm_bandwidth',str(a.bandwidth_gibits)];cmd[cmd.index('--random_forrest_execution_time_predictor_config_prediction_max_prefill_chunk_size')+1]='64'
  for option in ('--execution_mode','--dag_pd_config'):
   i=cmd.index(option);del cmd[i:i+2]
  for flag in ('--metrics_config_write_json_trace','--metrics_config_enable_chrome_trace'):cmd.remove(flag)
  execute(cmd,base,old)
  summaries=list(dag.glob('*/pd-summary.json'));metrics=list(old.glob('*/plots/pd_p2p_comm_time.csv'))
  assert len(summaries)==len(metrics)==1
  migration=json.loads(summaries[0].read_text())['migrations'][0];rows=list(csv.DictReader(metrics[0].open()));assert len(rows)==1
  baseline_seconds=float(rows[0]['pd_p2p_comm_time']);dag_seconds=migration['transfer_completed_at_s']-migration['transfer_started_at_s'];expected=(n+1)*524288/bw
  assert migration['wire_bytes']==n*524288
  assert math.isclose(baseline_seconds,expected,rel_tol=1e-10,abs_tol=1e-12)
  assert math.isclose(dag_seconds,expected,rel_tol=1e-10,abs_tol=1e-12),(n,dag_seconds,expected)
  graph_files=list(summaries[0].parent.glob('graphs/pd-*.graph.json'));assert len(graph_files)==1
  graph=json.loads(graph_files[0].read_text()); task=next(x for x in graph['tasks'] if x['kind']=='comm')
  assert task['metadata']['wire_bytes']==n*524288 and task['metadata']['billing_bytes']==(n+1)*524288
  results.append(dict(input_tokens=n,physical_kv_bytes=n*524288,billed_bytes=(n+1)*524288,baseline_seconds=baseline_seconds,dag_seconds=dag_seconds))
 write_json(out/'result.json',dict(status='passed',nature='synthetic functional fee parity; not hardware accuracy',baseline_commit='cef83f9ddd96540e3e9f48934f11335d52d54fce',bandwidth_bytes_per_s=bw,results=results))
 print(json.dumps(results,indent=2))
if __name__=='__main__':main()
