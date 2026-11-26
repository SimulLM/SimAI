import pathlib,json,collections,statistics,csv
p=pathlib.Path(__file__).parent
read=lambda f:[json.loads(x) for x in f.read_text().splitlines()]
req=read(p/'coverage/requests.jsonl');router={r['decode_id']:r for r in read(p/'router-events.jsonl') if r.get('decode_id')};waves=collections.defaultdict(list)
for r in req:waves[(r['length'],r['batch'],r['wave'],r['warmup'])].append(r)
windows=sorted((min(x['send_ns'] for x in rr),max(x['end_ns'] for x in rr),key) for key,rr in waves.items())
window_conflicts=[(a[2],b[2]) for a,b in zip(windows,windows[1:]) if a[1]>b[0]]
events=[];bad=[]
for f in p.glob('gpu-bounds-*.jsonl'):
 for e in read(f):
  if e.get('event')!='cuda_event_bounds':bad.append(e);continue
  if not(e['start_lower']<=e['start_upper'] and e['end_lower']<=e['end_upper'] and e['start_lower']<=e['end_upper']):bad.append({'bad_event':e});continue
  events.append(e)
producer_pids={e['pid'] for e in events if e['name']=='nccl_send'};out=[];proofs=[]
for key,requests in sorted(waves.items()):
 n,b,w,warm=key;start=min(x['send_ns'] for x in requests);end=max(x['end_ns'] for x in requests);ids={(router[x['backend_request_id']]['prefill_id']+'-0') for x in requests if x.get('backend_request_id') in router}
 forwards=[e for e in events if e['pid'] in producer_pids and e['name']=='model_forward' and set(e['metadata']['request_ids'])&ids and e['metadata']['query_lens'] and min(e['metadata']['query_lens'])>1]
 sends=[e for e in events if e['pid'] in producer_pids and e['name']=='nccl_send' and e['metadata']['bytes']>=100*1024*1024 and e['start_lower']>=start and e['end_upper']<=end]
 proven=[]
 for f in forwards:
  for s in sends:
   overlap_ns=min(f['end_lower'],s['end_lower'])-max(f['start_upper'],s['start_upper'])
   if overlap_ns>0:
    proven.append(overlap_ns/1e6);proofs.append({'input_tokens':n,'wave':w,'warmup':warm,'guaranteed_overlap_ms':overlap_ns/1e6,'forward':f,'send':s})
 out.append({'input_tokens':n,'requested_batch':b,'wave':w,'warmup':warm,'requests':len(requests),'mapped_ids':len(ids),'producer_prefill_forwards':len(forwards),'large_sends':len(sends),'guaranteed_overlap_pairs':len(proven),'max_guaranteed_overlap_ms':max(proven) if proven else 0})
with (p/'wave-overlap.csv').open('w',newline='') as f:
 writer=csv.DictWriter(f,fieldnames=out[0]);writer.writeheader();writer.writerows(out)
summary=[]
for n in sorted({x['input_tokens'] for x in out}):
 rr=[x for x in out if x['input_tokens']==n and not x['warmup']];summary.append({'input_tokens':n,'measured_waves':len(rr),'waves_with_guaranteed_overlap':sum(x['guaranteed_overlap_pairs']>0 for x in rr),'minimum_large_sends_per_wave':min((x['large_sends'] for x in rr),default=0),'fully_mapped_waves':sum(x['mapped_ids']==x['requests'] for x in rr),'largest_lower_bound_ms':max((x['max_guaranteed_overlap_ms'] for x in rr),default=0)})
result={'requests':len(req),'status_counts':dict(collections.Counter(str(x['status']) for x in req)),'summary':summary,'invalid_or_error_events':bad,'producer_pids':sorted(producer_pids),'client_wave_window_conflicts':window_conflicts,'limits':['CUDA event query polling bounds events by host CLOCK_MONOTONIC, but polling and instrumentation perturb execution','A positive lower bound proves intervals between recorded CUDA events overlap; events can enclose launch gaps and do not prove individual GPU kernels run simultaneously','NCCL sends lack request IDs; send-to-wave association uses non-overlapping client time windows and transfer payload threshold, not request-level matching','A missing positive overlap is inconclusive when bounds are wide; CUDA event queries are not formal E2E measurements','8 output tokens and diagnostic router buffering differ from formal 128-token streaming validation']}
if window_conflicts:raise RuntimeError(f'client waves overlap: {window_conflicts}')
if len(producer_pids)!=1:raise RuntimeError(f'unexpected producer pids {producer_pids}')
(p/'overlap-proofs.json').write_text(json.dumps(proofs,indent=2)+'\n')
(p/'overlap-audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
