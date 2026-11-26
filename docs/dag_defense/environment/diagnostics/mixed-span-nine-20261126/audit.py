import json,csv,pathlib,collections,statistics,math,hashlib
p=pathlib.Path(__file__).parent;waves=[json.loads(x) for x in (p/'waves.jsonl').read_text().splitlines()];assert len(waves)==40
ids={rid:w for w in waves for rid in w['outputs']};assert len(ids)==160
for w in waves:assert all(x['input_tokens']==2048 and x['output_tokens']==128 and x['finish_reason']=='length' for x in w['outputs'].values())
groups=collections.defaultdict(lambda:collections.defaultdict(list));shapes=collections.Counter();sources=list(p.glob('compute-events-*.jsonl'))
for f in sources:
 for line in f.open():
  e=json.loads(line);gs=e.get('groups') or [];lens=e.get('seq_lens') or [];val=(e.get('gpu_event_ms') or {}).get('full_model_forward')
  if len(gs)!=4 or len(lens)!=4 or any(g['is_prompt'] for g in gs) or val is None:continue
  if not all(g['request_id'] in ids for g in gs):continue
  ws=[ids[g['request_id']] for g in gs];w=ws[0]
  if any(x is not w for x in ws):continue
  pattern=tuple(sorted(x-min(lens) for x in lens));shapes[pattern]+=1
  if pattern!=(0,0,9,9):continue
  mean=sum(lens)//4;binval=((mean+15)//16)*16;groups[binval][w['wave']].append(float(val))
rows=[];samples=[]
for b,values in sorted(groups.items()):
 warm=[statistics.median(v) for wave,v in values.items() if wave<10];m=sorted(statistics.median(v) for wave,v in values.items() if wave>=10)
 rows.append({'input_tokens':2048,'actual_batch':4,'rounded_mean_context':b,'context_pattern':'0,0,9,9','warmup_waves':len(warm),'measured_waves':len(m),'median_forward_ms':statistics.median(m) if m else None,'min_ms':m[0] if m else None,'p95_ms':m[math.ceil(.95*len(m))-1] if m else None,'max_ms':m[-1] if m else None,'eligible':int(len(warm)>=10 and len(m)>=30)})
 samples.extend({'bin':b,'wave':wave,'warmup':int(wave<10),'steps':len(v),'median_forward_ms':statistics.median(v)} for wave,v in sorted(values.items()))
for name,rs in [('coverage.csv',rows),('wave-samples.csv',samples)]:
 with (p/name).open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=rs[0]);w.writeheader();w.writerows(rs)
result={'waves':len(waves),'requests':len(ids),'observed_patterns':{str(k):v for k,v in shapes.items()},'qualified_bins':sum(r['eligible'] for r in rows),'bins':len(rows),'sources':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in sources+[p/'waves.jsonl']},'limitations':['controlled single GPU, not PD end to end','CUDA synchronization perturbation','exact pattern only; cannot extrapolate to other spans','same service session','whole forward excludes CPU logits sampler KV router','not frozen']};(p/'audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
