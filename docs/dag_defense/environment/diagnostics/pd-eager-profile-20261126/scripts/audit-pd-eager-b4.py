"""Join eager producer by wave time and consumer by request IDs; exclude warmups."""
import bisect,collections,csv,json,re,statistics
from pathlib import Path
base=Path('/root/autodl-tmp/dag-handoff/runs/pd-mapped-eager-b4-20261126'); out=Path('/root/autodl-tmp/dag-handoff/runs/pd-mapped-eager-b4-audit-20261126');out.mkdir(exist_ok=False)
rows=[json.loads(x) for x in (base/'client-profile/requests.jsonl').read_text().splitlines()];spec=json.loads((base/'client-profile/client-spec.json').read_text()); waves=collections.defaultdict(list)
for r in rows:waves[(r['length'],r['batch'],r['wave'])].append(r)
wins=sorted((min(r['send_ns'] for r in v),max(r['end_ns'] for r in v),k,v) for k,v in waves.items());assert all(a[1]<=b[0] for a,b in zip(wins,wins[1:]));starts=[w[0] for w in wins]; byid={r['backend_request_id']+'-0':r for r in rows}; assert len(byid)==len(rows)
pids={}
for role in ('prefill','decode'):
 pids[role]=re.search(r'Started engine process with PID (\d+)',(base/f'{role}.log').read_text()).group(1)
groups=collections.defaultdict(list); rejected=collections.Counter();mapped=[]
for role,pid in pids.items():
 for line in (base/f'compute-events-{pid}.jsonl').read_text().splitlines():
  e=json.loads(line)
  if e.get('event')!='model_step':continue
  i=bisect.bisect_right(starts,e['host_start_ns'])-1
  if i<0 or e['host_start_ns']>wins[i][1]:rejected['outside_profile_windows']+=1;continue
  start,end,(n,wave_batch,wave),reqs=wins[i];q=e.get('query_lens') or [];seq=e.get('seq_lens') or [];ids=list((e.get('request_ids_to_seq_ids') or {}).keys())
  if not q or len(seq)<len(q) or any(x!=1 for x in seq[len(q):]):rejected['bad_shape']+=1;continue
  seq=seq[:len(q)]; phase='prefill' if all(x>1 for x in q) else 'decode' if all(x==1 for x in q) else 'mixed';nature='producer_prefill' if role=='prefill' and phase=='prefill' else 'consumer_decode' if role=='decode' and phase=='decode' else 'other'
  if nature=='other':continue
  if len(ids)!=len(q):rejected['id_batch_size_mismatch']+=1;continue
  if nature=='consumer_decode' and (any(i not in byid for i in ids) or any(byid[i]['wave']!=wave or byid[i]['length']!=n or byid[i]['batch']!=wave_batch for i in ids)):
   rejected['consumer_id_mismatch']+=1;continue
  if any(s<n or s>n+8 for s in seq):rejected['context_mismatch']+=1;continue
  # Exclude steps whose host synchronization ends after the client wave completes.
  if e['host_after_sync_ns']>end or (nature=='consumer_decode' and any(e['host_after_sync_ns']>byid[i]['end_ns'] for i in ids)):rejected['host_sync_after_client']+=1;continue
  value=e.get('gpu_event_ms',{}).get('full_model_forward')
  if value is None:rejected['missing_forward']+=1;continue
  warm=wave<spec['warmup_waves']; groups[(nature,n,len(q))].append((warm,float(value),wave_batch,wave))
  mapped.append({'nature':nature,'input_tokens':n,'wave_batch':wave_batch,'wave':wave,'actual_batch':len(q),'warmup':warm,'ids':'|'.join(ids),'mapping':'consumer_id' if nature=='consumer_decode' else 'producer_wave_only','forward_ms':value,'host_start_ns':e['host_start_ns'],'host_sync_ns':e['host_after_sync_ns']})
coverage=[]
for (nature,n,b),v in sorted(groups.items()):
 warm_waves={(x[2],x[3]) for x in v if x[0]}; measured_waves={(x[2],x[3]) for x in v if not x[0]}; vals=[x[1] for x in v if not x[0]];coverage.append({'nature':nature,'input_tokens':n,'actual_batch':b,'warmup_events':sum(x[0] for x in v),'measured_events':len(vals),'warmup_waves':len(warm_waves),'measured_waves':len(measured_waves),'median_forward_ms':statistics.median(vals) if vals else '', 'enough':len(warm_waves)>=10 and len(measured_waves)>=30})
for name,data in [('coverage.csv',coverage),('mapped.csv',mapped)]:
 with (out/name).open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=data[0]);w.writeheader();w.writerows(data)
expected=[('producer_prefill',512,4)]+[('consumer_decode',n,4) for n in (512,575,2048,2175)];idx={(r['nature'],r['input_tokens'],r['actual_batch']):r for r in coverage};missing=[x for x in expected if x not in idx or not idx[x]['enough']]; report={'status':'shape_coverage_only_passed' if not missing else 'blocked','client_requests':len(rows),'client_waves':len(wins),'pids':pids,'required_points':len(expected),'passed_points':len(expected)-len(missing),'missing':missing,'rejected_events':dict(rejected),'limitations':['consumer ID join is direct, producer association only by non-overlapping wave time','CUDA event forward excludes KV transfer, logits and sampler; GPU stream timing and synchronization can perturb execution','shape coverage does not prove cost/boundary compatibility or formal validation']};(out/'summary.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
