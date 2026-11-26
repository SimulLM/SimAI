import pathlib,json,collections,statistics,csv
p=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/token-gpu-diagnostic-20261126');rr=[json.loads(x) for x in (p/'client/requests.jsonl').read_text().splitlines()];events=collections.defaultdict(list);invalid=[]
for f in (p/'server').glob('gpu-bounds-*.jsonl'):
 for line in f.read_text().splitlines():
  e=json.loads(line)
  if e.get('event')!='cuda_event_bounds':invalid.append(e);continue
  if e['name']!='model_forward':continue
  meta=e['metadata'];ids=meta.get('request_ids',[]);q=meta.get('query_lens',[])
  if len(ids)==1 and q==[1]:events[ids[0]].append(e)
rows=[];errors=[]
for r in rr:
 rid=(r.get('decode_id') or '')+'-0';ev=sorted(events[rid],key=lambda x:x['start_lower']);tok=r['tokens'];issues=[]
 if len(ev)!=63:issues.append(f'decode_events={len(ev)}')
 if len(tok)!=64 or [x['count'] for x in tok]!=list(range(1,65)):issues.append('token sequence')
 if r.get('status')!=200 or not r.get('done'):issues.append('request status')
 if issues:errors.append({'index':r['index'],'issues':issues})
 for i,(e,a,b) in enumerate(zip(ev,tok,tok[1:]),1):
  lower=max(0,(e['end_lower']-e['start_upper'])/1e6);upper=max(0,(e['end_upper']-e['start_lower'])/1e6);gap=(b['received_ns']-a['received_ns'])/1e6
  rows.append({'index':r['index'],'warmup':r['warmup'],'decode_step':i,'request_id':rid,'token_gap_ms':gap,'gpu_event_lower_ms':lower,'gpu_event_upper_ms':upper,'gpu_start_uncertainty_ms':(e['start_upper']-e['start_lower'])/1e6,'gpu_end_uncertainty_ms':(e['end_upper']-e['end_lower'])/1e6,'gpu_end_upper_before_client_next':e['end_upper']<=b['received_ns']})
with (p/'step-bounds.csv').open('w',newline='') as f:
 if rows:w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
meas=[r for r in rows if not r['warmup']];groups=[]
for label,subset in [('gap_le_20',[r for r in meas if r['token_gap_ms']<=20]),('gap_gt_20',[r for r in meas if r['token_gap_ms']>20])]:
 groups.append({'group':label,'n':len(subset),'median_token_gap_ms':statistics.median(x['token_gap_ms'] for x in subset) if subset else None,'median_gpu_lower_ms':statistics.median(x['gpu_event_lower_ms'] for x in subset) if subset else None,'median_gpu_upper_ms':statistics.median(x['gpu_event_upper_ms'] for x in subset) if subset else None,'median_start_uncertainty_ms':statistics.median(x['gpu_start_uncertainty_ms'] for x in subset) if subset else None,'median_end_uncertainty_ms':statistics.median(x['gpu_end_uncertainty_ms'] for x in subset) if subset else None,'gpu_end_upper_before_client_next':sum(x['gpu_end_upper_before_client_next'] for x in subset)})
res={'status':'complete' if len(rr)==20 and not errors and not invalid else 'incomplete','request_count':len(rr),'measured_step_count':len(meas),'errors':errors,'invalid_events':invalid,'groups':groups,'limits':['Nonblocking CUDA event polling and Python hooks perturb scheduling; separate diagnostic, not formal E2E','GPU event interval bounds may include asynchronous queue and host launch gaps, not exact kernel duration','Per-request sequence ordinal aligns one post-first token interval with one decode model forward; asynchronous processing and output buffering may shift observed client gaps','If event bounds are wide the inference is inconclusive; no GPU/CPU causation proved','No validation results used to tune fees']};(p/'audit-gpu.json').write_text(json.dumps(res,indent=2)+'\n');print(json.dumps(res,indent=2));raise SystemExit(0 if res['status']=='complete' else 1)
