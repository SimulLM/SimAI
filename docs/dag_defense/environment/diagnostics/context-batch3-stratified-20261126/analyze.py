import csv,json,pathlib,collections,statistics,hashlib,math
p=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/pd-context-batch3-20261126'); out=pathlib.Path(__file__).parent
read=lambda f:[json.loads(x) for x in f.read_text().splitlines() if x]
req=read(p/'client/requests.jsonl'); route={r['decode_id']:r for r in read(p/'router-events.jsonl') if r.get('decode_id')};ids={route[r['backend_request_id']]['decode_id']+'-0':r for r in req if r.get('backend_request_id') in route}
groups=collections.defaultdict(lambda:collections.defaultdict(list))
for f in p.glob('compute-events-*.jsonl'):
 for e in read(f):
  if e.get('event')!='model_step':continue
  mapping=e.get('request_ids_to_seq_ids') or {};matches=[ids[x] for x in mapping if x in ids]; decode=[x for x in e.get('groups',[]) if x['request_id'] in ids and not x['is_prompt']]
  if len(matches)!=3 or len(mapping)!=3 or len(decode)!=3:continue
  if len({(r['length'],r['batch'],r['wave'],r['warmup']) for r in matches})!=1:continue
  lens=e.get('seq_lens') or [];value=(e.get('gpu_event_ms') or {}).get('full_model_forward')
  if len(lens)!=3 or value is None or max(lens)-min(lens)>1 or matches[0]['length']!=1024:continue
  binval=((int(sum(lens)/3)+15)//16)*16;r=matches[0];wave=(r['batch'],r['wave'],r['warmup']);groups[(binval,wave)][max(lens)-min(lens)].append(float(value))
rows=[]; wave_rows=[]
for b in sorted({k[0] for k in groups}):
 bins=[(wave,v) for (binval,wave),v in groups.items() if binval==b];warm=[];measured=[];classes={0:[],1:[]}
 for wave,v in bins:
  allvals=[x for a in v.values() for x in a];med=statistics.median(allvals);iswarm=wave[2]
  (warm if iswarm else measured).append(med)
  if not iswarm:
   for typ,vals in v.items():classes[typ].append(statistics.median(vals))
  wave_rows.append({'bin':b,'requested_batch':wave[0],'wave':wave[1],'warmup':int(iswarm),'pooled_wave_median_ms':med,'uniform_step_count':len(v.get(0,[])),'mixed_step_count':len(v.get(1,[])),'uniform_median_ms':statistics.median(v[0]) if 0 in v else '', 'mixed_median_ms':statistics.median(v[1]) if 1 in v else ''})
 if not measured:continue
 a=sorted(measured);q=lambda f:a[max(0,math.ceil(f*len(a))-1)];m=statistics.median(a); med0=statistics.median(classes[0]) if classes[0] else None;med1=statistics.median(classes[1]) if classes[1] else None
 rows.append({'bin':b,'warmup_waves':len(warm),'measured_waves':len(measured),'pooled_median_ms':m,'min_ms':a[0],'p95_ms':q(.95),'max_ms':a[-1],'uniform_waves':len(classes[0]),'mixed_waves':len(classes[1]),'uniform_median_ms':med0,'mixed_median_ms':med1,'stratum_median_gap_pct':abs(med0-med1)/m*100 if med0 is not None and med1 is not None else None})
for name,data in [('wave-samples.csv',wave_rows),('summary.csv',rows)]:
 with (out/name).open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=data[0]);w.writeheader();w.writerows(data)
result={'status':'diagnostic_only_not_a_frozen_cost','input_tokens':1024,'actual_batch':3,'rows':rows,'source_sha256':{str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in [p/'client/requests.jsonl',p/'router-events.jsonl',*p.glob('compute-events-*.jsonl')]},'limitations':['10/30 applies only to broad composition-pooled points; individual strata below threshold','wave samples within a service session not independent restarts','rounding and observed one-token context span do not cover arbitrary contexts','stratum difference is descriptive and confounded with wave state; not causal or a universal bound','CUDA event synchronization perturbs timing and can include stream gaps','forward excludes CPU, logits, sampler, KV and router; replacement not addition','no validation completion used']};(out/'audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(rows,indent=2))
