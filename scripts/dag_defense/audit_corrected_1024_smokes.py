"""Verify saved corrected smokes, including simulator-effective token lengths."""
import csv,json,math,pathlib,sys
base=pathlib.Path(sys.argv[1]); out=pathlib.Path(sys.argv[2]); runs=['pd-decode-pull-smoke-v3-20261126','pd-decode-pull-interleave-smoke-v2-20261126','pd-physical-fee-smoke-v2-20261126'];result=[]
for run in runs:
 p=base/run;files=list((p/'dag').glob('*/pd-summary.json'))
 if len(files)!=1:raise ValueError('missing/ambiguous DAG output')
 d=json.loads(files[0].read_text());case={'run':run,'dag_summary':d['status'],'variants':{},'transfer_count':len(d['migrations'])}
 for mode in ('dag','adapted_baseline'):
  q=p/mode
  if not q.exists():continue
  rc=int((q/'process-returncode').read_text());files=list(q.glob('*/request_metrics.csv'))
  if len(files)!=1 or rc!=0:raise ValueError('simulator process failed or metrics missing')
  metrics=list(csv.DictReader(files[0].open()));expected=2 if 'interleave' in run else 3
  if len(metrics)!=expected or any(float(x['request_num_prefill_tokens'])!=1024 or float(x['request_num_decode_tokens'])!=128 for x in metrics):raise ValueError('actual token lengths or count mismatch')
  case['variants'][mode]={'exit_code':rc,'requests':len(metrics),'prefill_tokens':1024,'decode_tokens':128}
 if d['status']!='completed' or any(m['wire_bytes']!=536870912 for m in d['migrations']):raise ValueError('DAG physical KV count or completion mismatch')
 if 'physical-fee' in run:
  cfg=json.loads((p/'pd-config.json').read_text())
  for m in d['migrations']:
   expected=cfg['latency_s']+m['wire_bytes']/cfg['bandwidth_bytes_per_s']
   if not math.isclose(expected,m['transfer_completed_at_s']-m['transfer_started_at_s'],abs_tol=1e-12):raise ValueError('physical fee arithmetic mismatch')
  case['verified_fee_formula']=True
 if 'interleave' in run:
  m=sorted(d['migrations'],key=lambda x:int(x['request_id']))
  if not m[0]['first_decode_start_s']<m[1]['transfer_started_at_s']<m[0]['completed_at_s']:raise ValueError('expected interleave missing')
  case['verified_pull_between_first_and_last_decode']=True
 result.append(case)
output={'status':'passed_posthoc','results':result,'note':'Two initial corrected smoke wrappers exited 1 while parsing baseline CSV 1024.0 after simulator exit 0. This verifier checks their saved output and avoids rerunning; failure logs are retained.'};out.write_text(json.dumps(output,indent=2)+'\n');print(json.dumps(output,indent=2))
