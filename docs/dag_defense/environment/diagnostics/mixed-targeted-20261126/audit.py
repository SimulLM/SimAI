import json,csv,pathlib,collections,statistics,math,hashlib
p=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/mixed-targeted-20261126'); out=pathlib.Path(__file__).parent
assert (p/'exit').read_text().strip()=='0'
waves=[json.loads(x) for x in (p/'waves.jsonl').read_text().splitlines()]; assert len(waves)==80
ids={rid:w for w in waves for rid in w['outputs']};assert len(ids)==240
for w in waves:
 n=1024 if w['case']=='1024-mixed2' else 2048
 assert all(x['input_tokens']==n and x['output_tokens']==128 and x['finish_reason']=='length' for x in w['outputs'].values())
groups=collections.defaultdict(lambda:collections.defaultdict(list));shapes=collections.Counter();sources=list(p.glob('compute-events-*.jsonl'));assert sources
for f in sources:
 for line in f.open():
  e=json.loads(line);gs=e.get('groups') or [];lens=e.get('seq_lens') or [];val=(e.get('gpu_event_ms') or {}).get('full_model_forward')
  if not gs or len(gs)!=len(lens) or any(g['is_prompt'] for g in gs) or val is None:continue
  if not all(g['request_id'] in ids for g in gs):continue
  ws=[ids[g['request_id']] for g in gs];w=ws[0]
  if any(x is not w for x in ws):continue
  pat=tuple(sorted(x-min(lens) for x in lens));case=w['case'];shapes[(case,pat)]+=1
  target=(0,1) if case=='1024-mixed2' else (0,0,8,8)
  if pat!=target:continue
  n=1024 if case=='1024-mixed2' else 2048; b=((sum(lens)//len(lens)+15)//16)*16
  if not n < b <= n+128: continue
  groups[(case,b)][w['wave']].append(float(val))
rows=[];samples=[]
for (case,b),values in sorted(groups.items()):
 warm=[statistics.median(v) for wave,v in values.items() if wave<10];m=sorted(statistics.median(v) for wave,v in values.items() if wave>=10)
 rows.append({'case':case,'input_tokens':1024 if case=='1024-mixed2' else 2048,'actual_batch':2 if case=='1024-mixed2' else 4,'rounded_mean_context':b,'context_pattern':'0,1' if case=='1024-mixed2' else '0,0,8,8','warmup_waves':len(warm),'measured_waves':len(m),'median_forward_ms':statistics.median(m) if m else None,'min_ms':m[0] if m else None,'p95_ms':m[math.ceil(.95*len(m))-1] if m else None,'max_ms':m[-1] if m else None,'eligible':int(len(warm)>=10 and len(m)>=30)})
 samples.extend({'case':case,'bin':b,'wave':wave,'warmup':int(wave<10),'steps':len(v),'median_forward_ms':statistics.median(v)} for wave,v in sorted(values.items()))
for name,rs in [('coverage.csv',rows),('wave-samples.csv',samples)]:
 if rs:
  with (out/name).open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=rs[0]);w.writeheader();w.writerows(rs)
result={'waves':len(waves),'requests':len(ids),'observed_patterns':{str(k):v for k,v in shapes.items()},'coverage':rows,'sources':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in sources+[p/'waves.jsonl',p/'profile.py',p/'run.sh']},'limitations':['offline single GPU, not PD E2E','per-step CUDA synchronization perturbation','exact measured patterns only','same service session','full forward excludes KV CPU logits sampler router','not frozen']}
(out/'audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
