"""Replay first real calibration request in isolation using existing candidate costs."""
import concurrent.futures,csv,hashlib,json,os,pathlib,subprocess,sys,time
src=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/pd-pull-calibration-replay-20261126/serial-0')
out=pathlib.Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=False)
rows=json.loads((src/'request-map.json').read_text());mapping=rows[0]
assert mapping['simulator_request_id']==0
with (src/'trace.csv').open() as f: original=list(csv.DictReader(f))
assert len(original)==32 and float(original[0]['arrived_at'])==0 and original[0]['num_prefill_tokens']=='512' and original[0]['num_decode_tokens']=='64'
trace=out/'trace.csv'
with trace.open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(original[0]));w.writeheader();w.writerow(original[0])
(out/'source-request.json').write_text(json.dumps(mapping,indent=2)+'\n')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def run(name,repo):
 dest=out/name;dest.mkdir();cmd=json.loads((src/name/'command.json').read_text())
 changes={'--trace_request_generator_config_trace_file':str(trace),'--random_forrest_execution_time_predictor_config_simai_dir':str(dest),'--metrics_config_output_dir':str(dest),'--metrics_config_cache_dir':str(dest/'cache')}
 for flag,value in changes.items():
  assert cmd.count(flag)==1;cmd[cmd.index(flag)+1]=value
 (dest/'command.json').write_text(json.dumps(cmd,indent=2)+'\n')
 env=dict(os.environ,PYTHONPATH=f'{repo}/vidur-alibabacloud:{repo}',WANDB_MODE='disabled',PYTHONDONTWRITEBYTECODE='1')
 with (dest/'process.log').open('w') as log:
  try: r=subprocess.run(cmd,cwd=repo,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=900);code=r.returncode
  except subprocess.TimeoutExpired:code=124
 (dest/'exit').write_text(str(code)+'\n');return {'version':name,'exit':code}
(out/'manifest.json').write_text(json.dumps({'status':'diagnostic_not_frozen','note':'Isolated first measured 512/64 calibration request; same candidate costs, adapted baseline not pristine','mapping':mapping,'trace_sha256':sha(trace),'source_trace_sha256':sha(src/'trace.csv')},indent=2)+'\n')
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
 futures=[pool.submit(run,n,p) for n,p in [('dag','/root/autodl-tmp/SimAI-handoff'),('adapted_baseline','/root/autodl-tmp/SimAI-baseline')]]
 results=[x.result() for x in futures]
(out/'status.json').write_text(json.dumps({'results':results,'formal_validation':False},indent=2)+'\n')
sys.exit(0 if all(x['exit']==0 for x in results) else 1)
