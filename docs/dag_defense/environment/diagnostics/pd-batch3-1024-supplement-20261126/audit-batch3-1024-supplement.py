"""Pool distinct waves of independent matched profiling runs without mixing context shapes."""
import collections,csv,hashlib,json,pathlib,statistics,sys
runs=[pathlib.Path(p) for p in sys.argv[1:-1]];output=pathlib.Path(sys.argv[-1]);output.mkdir(exist_ok=False)
groups=collections.defaultdict(lambda:collections.defaultdict(list));discard=collections.Counter();sources={};run_summary=[]
for p in runs:
 if (p/'exit').read_text().strip()!='0':raise ValueError(f'failed run {p}')
 def read(f):
  sources[str(f)]=hashlib.sha256(f.read_bytes()).hexdigest()
  return [json.loads(x) for x in f.read_text().splitlines()]
 req=read(p/'client/requests.jsonl');route={x['decode_id']:x for x in read(p/'router-events.jsonl') if x.get('decode_id')};ids={route[x['backend_request_id']]['decode_id']+'-0':x for x in req if x.get('backend_request_id') in route}
 if len(req)!=len(ids) or any(x.get('status')!=200 or x.get('usage',{}).get('prompt_tokens')!=1024 or x.get('usage',{}).get('completion_tokens')!=128 for x in req if x['length']==1024):raise ValueError(f'bad request mapping {p}')
 run_summary.append({'run':str(p),'requests':len(req),'mapped':len(ids)})
 for f in sorted(p.glob('compute-events-*.jsonl')):
  for e in read(f):
   if e.get('event')!='model_step':continue
   mapping=e.get('request_ids_to_seq_ids') or {};matches=[ids[x] for x in mapping if x in ids and ids[x]['length']==1024];decode=[x for x in e.get('groups',[]) if x['request_id'] in ids and ids[x['request_id']]['length']==1024 and not x['is_prompt']]
   if not matches or not decode:continue
   if len(matches)!=len(mapping) or len(decode)!=len(mapping):discard['mixed_phase']+=1;continue
   if len({(r['length'],r['batch'],r['wave'],r['warmup']) for r in matches})!=1:discard['mixed_wave']+=1;continue
   lens=e.get('seq_lens') or [];value=(e.get('gpu_event_ms') or {}).get('full_model_forward')
   if len(lens)!=len(mapping) or value is None:discard['missing_shape_or_forward']+=1;continue
   span=max(lens)-min(lens)
   if span>1:discard['context_span_gt_1']+=1;continue
   mean=int(sum(lens)/len(lens));r=matches[0];key=(len(mapping),((mean+15)//16)*16,int(span>0));wave=(str(p),r['batch'],r['wave'],r['warmup']);groups[key][wave].append(float(value))
rows=[]
for (batch,context,mixed),waves in sorted(groups.items()):
 warm=[statistics.median(v) for (_,_,_,w),v in waves.items() if w];meas=[statistics.median(v) for (_,_,_,w),v in waves.items() if not w]
 rows.append({'input_tokens':1024,'actual_batch':batch,'rounded_mean_context':context,'mixed_context':mixed,'warmup_waves':len(warm),'measured_waves':len(meas),'median_forward_ms':statistics.median(meas) if meas else '', 'eligible':int(len(warm)>=10 and len(meas)>=30),'waves_by_run':json.dumps({str(p):{'warmup':sum(1 for key in waves if key[0]==str(p) and key[3]),'measured':sum(1 for key in waves if key[0]==str(p) and not key[3])} for p in runs},sort_keys=True)})
with (output/'forward-context-bins.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
result={'status':'independent_candidate_not_frozen','runs':run_summary,'source_hashes':sources,'discarded_steps':dict(discard),'batch3': [r for r in rows if r['actual_batch']==3], 'contract':'Per-wave median; independent runs distinguished by path; mixed and uniform shapes are never pooled. >=10 warmup and >=30 measured distinct waves per cell. Full forward only; instrumentation perturbs timings. Not a complete service cost or formal validation.'}
(output/'manifest.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
