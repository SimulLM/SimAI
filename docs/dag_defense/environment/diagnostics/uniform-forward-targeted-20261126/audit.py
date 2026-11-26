import collections,csv,json,pathlib,statistics,math,hashlib
p=pathlib.Path(__file__).parent;waves=[json.loads(x) for x in (p/'waves.jsonl').read_text().splitlines()];assert len(waves)==80
requests={};groups=collections.defaultdict(lambda:collections.defaultdict(list));discard=collections.Counter()
for w in waves:
 assert len(w['outputs'])==w['batch'] and all(x['input_tokens']==w['input_length'] and x['output_tokens']==128 and x['finish_reason']=='length' for x in w['outputs'])
 for x in w['outputs']:assert x['request_id'] not in requests;requests[x['request_id']]=w
sources=list(p.glob('compute-events-*.jsonl'));assert sources
for f in sources:
 for line in f.open():
  e=json.loads(line)
  if e.get('event')!='model_step':continue
  groups_raw=e.get('groups') or [];ids=[x['request_id'] for x in groups_raw]; lens=e.get('seq_lens') or [];val=(e.get('gpu_event_ms') or {}).get('full_model_forward')
  if len(ids) not in (2,3) or len(lens)!=len(ids) or any(x.get('is_prompt') for x in groups_raw) or val is None:discard['other']+=1;continue
  if any(x not in requests for x in ids):discard['unknown_id']+=1;continue
  ws=[requests[x] for x in ids];w=ws[0]
  if any(x is not w for x in ws) or max(lens)!=min(lens):discard['mixed_wave_or_context']+=1;continue
  n=w['input_length'];batch=w['batch'];ctx=lens[0]
  if len(ids)!=batch:discard['not_target_batch']+=1;continue
  if not n+1<=ctx<=n+127:discard['out_of_range']+=1;continue
  key=(n,batch,((ctx+15)//16)*16);groups[key][w['wave']].append(val)
rows=[];sample=[]
for n,batch in ((2048,2),(1024,3)):
 for ctx in range(n+16,n+129,16):
  data=groups[(n,batch,ctx)];warm=[statistics.median(v) for wave,v in data.items() if wave<10];meas=[statistics.median(v) for wave,v in data.items() if wave>=10];a=sorted(meas)
  rows.append({'input_tokens':n,'actual_batch':batch,'rounded_mean_context':ctx,'mixed_context':0,'warmup_waves':len(warm),'measured_waves':len(meas),'median_forward_ms':statistics.median(meas) if a else None,'min_ms':a[0] if a else None,'p95_ms':a[math.ceil(len(a)*.95)-1] if a else None,'max_ms':a[-1] if a else None,'eligible':int(len(warm)>=10 and len(meas)>=30)})
  sample.extend({'input_tokens':n,'rounded_mean_context':ctx,'wave':wave,'warmup':int(wave<10),'steps':len(v),'median_forward_ms':statistics.median(v)} for wave,v in sorted(data.items()))
for name,rs in [('coverage.csv',rows),('wave-samples.csv',sample)]:
 with (p/name).open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=rs[0]);w.writeheader();w.writerows(rs)
result={'status':'independent_single_gpu_diagnostic','waves':len(waves),'requests':len(requests),'eligible':sum(x['eligible'] for x in rows),'expected_cells':len(rows),'discarded':dict(discard),'sources':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in sources+[p/'waves.jsonl']},'limitations':['single GPU offline vLLM, not PD E2E or proof of same workload distribution','GPU synchronization and hooks perturb timing and can include GPU gaps','forward excludes logits sampler CPU connector and router','wave observations share one service session','targeted uniform batch 2 or 3 only; other shapes remain uncovered','not frozen and no validation data used']};(p/'audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
