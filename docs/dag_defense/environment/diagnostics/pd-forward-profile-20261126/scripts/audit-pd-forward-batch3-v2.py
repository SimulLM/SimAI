"""Audit diagnostic model steps by unique non-overlapping client wave windows.
Time association is not request-ID mapping; startup and ambiguity are excluded.
"""
import bisect,csv,glob,json,statistics,collections,hashlib
from pathlib import Path
base=Path('/root/autodl-tmp/dag-handoff/runs/pd-forward-batch3-20261126'); out=Path('/root/autodl-tmp/dag-handoff/runs/pd-forward-batch3-audit-v2-20261126'); out.mkdir(exist_ok=False)
rows=[json.loads(x) for x in (base/'client-full/requests.jsonl').read_text().splitlines()]; waves=collections.defaultdict(list)
for r in rows: waves[(r['length'],r['batch'],r['wave'])].append(r)
wins=sorted((min(r['send_ns'] for r in v), max(r['end_ns'] for r in v), k, v) for k,v in waves.items()); assert all(a[1] <= b[0] for a,b in zip(wins,wins[1:])); starts=[x[0] for x in wins]
groups=collections.defaultdict(list); rejected=collections.Counter(); per_event=[]
for path in sorted(glob.glob(str(base/'compute-events-*.jsonl'))):
 pid=int(Path(path).stem.split('-')[-1]); role={75064:'producer',75059:'consumer'}[pid]
 for line in open(path):
  e=json.loads(line)
  if e.get('event')!='model_step': continue
  i=bisect.bisect_right(starts,e['host_start_ns'])-1
  if i<0 or e['host_start_ns']>wins[i][1]: rejected['outside_client_wave']+=1; continue
  start,end,(length,wave_batch,wave),reqs=wins[i]; q=e.get('query_lens') or []; lens=e.get('seq_lens') or []
  if not q or len(lens)<len(q) or any(x!=1 for x in lens[len(q):]): rejected['missing_or_nonpadding_shape']+=1; continue
  lens=lens[:len(q)]  # CUDA graph adds dummy sequence length 1 after actual queries
  if e['host_after_sync_ns']>end: rejected['end_after_wave']+=1; continue
  if any(r.get('status')!=200 or r.get('usage',{}).get('prompt_tokens')!=length or r.get('usage',{}).get('completion_tokens')!=2 for r in reqs): rejected['client_failure']+=1; continue
  phase='prefill' if all(x>1 for x in q) else 'decode' if all(x==1 for x in q) else 'mixed'
  if phase=='mixed' or any(x<length or x>length+2 for x in lens): rejected['shape_mismatch']+=1; continue
  # A producer decode step is prefill-side sampling. Consumer prefill includes KV receive;
  # neither is a standalone transformer prefill/decode measurement.
  nature='producer_prefill' if role=='producer' and phase=='prefill' else 'consumer_decode' if role=='consumer' and phase=='decode' else role+'_'+phase+'_other'
  key=(nature,length,len(q)); eligible=wave>=20
  forward=e.get('gpu_event_ms',{}).get('full_model_forward')
  if forward is None and nature in ('producer_prefill','consumer_decode'):
   rejected['missing_forward']+=1; continue
  groups[key].append((wave,eligible,float(forward if forward is not None else e['step_gpu_ms'])))
  per_event.append(dict(role=role,phase=phase,nature=nature,input_tokens=length,wave_batch=wave_batch,wave=wave,actual_batch=len(q),seq_lens='|'.join(map(str,lens)),warmup=int(not eligible),step_gpu_ms=e['step_gpu_ms'],forward_gpu_ms=forward,host_start_ns=e['host_start_ns'],host_after_sync_ns=e['host_after_sync_ns']))
coverage=[]
for (nature,n,b),vals in sorted(groups.items()):
 warm=sum(not x[1] for x in vals); measured=[x[2] for x in vals if x[1]]; coverage.append(dict(nature=nature,input_tokens=n,actual_batch=b,warmup_events=warm,measured_events=len(measured),median_forward_gpu_ms=statistics.median(measured) if measured else '',gate_at_least_10_warmup_and_30_measured=warm>=10 and len(measured)>=30))
for name,data in [('events-mapped.csv',per_event),('coverage.csv',coverage)]:
 with (out/name).open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=data[0]); w.writeheader(); w.writerows(data)
expected=[(role,n,b) for role in ('producer_prefill','consumer_decode') for n in (512,1024,2048) for b in (1,2,4)]
index={(r['nature'],r['input_tokens'],r['actual_batch']):r for r in coverage}; missing=[{'nature':x[0],'input_tokens':x[1],'actual_batch':x[2],'reason':'insufficient warmup or measured events' if x in index else 'no eligible event'} for x in expected if x not in index or not index[x]['gate_at_least_10_warmup_and_30_measured']]
summary={'status':'blocked' if missing else 'coverage_passed_only','method':'unique non-overlapping client wave time interval; not request ID mapping','client_requests':len(rows),'client_waves':len(wins),'rejected_events':dict(rejected),'expected_points':len(expected),'passed_points':len(expected)-len(missing),'missing_points':missing,'limitations':['same host monotonic clock; event association is per wave, not per request','forward event brackets model execution excluding connector recv/send, logits and sampler; CUDA event includes stream ordering and may include GPU idle gaps','consumer prefill / KV receive not counted as transformer prefill','events require accurate source role and separate non-overlapping billing contract']}; (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n'); print(json.dumps(summary,indent=2))
