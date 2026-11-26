import csv,json,pathlib,collections,statistics,sys
p=pathlib.Path(sys.argv[1]); read=lambda f:[json.loads(x) for x in f.read_text().splitlines()]
requests=read(p/'client/requests.jsonl'); routes={x.get('decode_id'):x for x in read(p/'router-events.jsonl') if x.get('decode_id')}; idx={};errors=[]
for r in requests:
 route=routes.get(r.get('backend_request_id'))
 if not route: errors.append({'id':r.get('backend_request_id'),'reason':'router missing'});continue
 idx[route['decode_id']+'-0']=r
seen=collections.Counter(); groups=collections.defaultdict(lambda:collections.defaultdict(list));bad=collections.Counter();source=[]
for f in p.glob('compute-events-*.jsonl'):
 with f.open() as stream:
  for line in stream:
   e=json.loads(line)
   if e.get('event')!='model_step':continue
   m=e.get('request_ids_to_seq_ids') or {}; relevant=[idx[x] for x in m if x in idx]
   if not relevant:continue
   phase=[g for g in e['groups'] if g['request_id'] in idx and not g['is_prompt']]
   if not phase:continue
   for g in phase:seen[g['request_id']]+=1
   if len(relevant)!=len(m) or len(phase)!=len(m):bad['mixed_request_phase']+=1;continue
   if len({(r['length'],r['batch'],r['wave'],r['warmup']) for r in relevant})!=1:bad['mixed_wave']+=1;continue
   lens=e.get('seq_lens') or []
   if len(lens)!=len(m) or len(set(lens))!=1:bad['mixed_context']+=1;continue
   vals=e.get('gpu_event_ms',{});value=vals.get('full_model_forward')
   if value is None:bad['missing_forward']+=1;continue
   r=relevant[0];delta=lens[0]-r['length']; actual=len(m)
   if not 1<=delta<=127:bad['context_out_of_range']+=1;continue
   key=(r['length'],actual,delta);wk=(r['batch'],r['wave'],r['warmup']);groups[key][wk].append(value)
for rid,r in idx.items():
 if seen[rid]!=127:errors.append({'id':rid,'reason':'decode_step_count','found':seen[rid]})
summary=[]
for key,waves in sorted(groups.items()):
 warm=[statistics.median(v) for (_,_,w),v in waves.items() if w];meas=[statistics.median(v) for (_,_,w),v in waves.items() if not w]
 summary.append({'input_tokens':key[0],'actual_batch':key[1],'context_offset':key[2],'warmup_waves':len(warm),'measured_waves':len(meas),'forward_ms':statistics.median(meas) if meas else None,'coverage_ok':len(warm)>=10 and len(meas)>=30})
with (p/'context-coverage.csv').open('w',newline='') as f:
 if summary:
  w=csv.DictWriter(f,fieldnames=summary[0]);w.writeheader();w.writerows(summary)
missing=[{'input_tokens':n,'actual_batch':b,'context_offset':d} for n in (1024,2048) for b in (1,2,3,4) for d in range(1,128) if not any(x['input_tokens']==n and x['actual_batch']==b and x['context_offset']==d and x['coverage_ok'] for x in summary)]
result={'requests':len(requests),'status_counts':dict(collections.Counter(str(r.get('status')) for r in requests)),'mapped':len(idx),'errors':errors,'discarded_steps':dict(bad),'points':len(summary),'passing_points':sum(x['coverage_ok'] for x in summary),'missing':missing,'limits':'GPU event includes host/queue gaps; detailed synchronized profiler, not E2E; context grouping requires same wave and equal sequence lengths; medians per distinct client wave; actual batch size and requested concurrency differ. Not a complete cost or frozen profile.'}
(p/'context-audit.json').write_text(json.dumps(result,indent=2)+'\n');print('requests',len(requests),'mapped',len(idx),'errors',len(errors),'points',len(summary),'pass',result['passing_points'],'missing',len(missing),'discarded',dict(bad))
