import csv,json,pathlib,collections,statistics,hashlib,math
p=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/pd-context-supplement-20261126'); out=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/pd-context-bin-supplement-20261126');out.mkdir(exist_ok=False)
read=lambda f:[json.loads(x) for x in f.read_text().splitlines()]
req=read(p/'client/requests.jsonl'); route={r['decode_id']:r for r in read(p/'router-events.jsonl') if r.get('decode_id')}; ids={route[r['backend_request_id']]['decode_id']+'-0':r for r in req if r.get('backend_request_id') in route}; groups=collections.defaultdict(lambda:collections.defaultdict(list));discard=collections.Counter()
for f in p.glob('compute-events-*.jsonl'):
 for e in read(f):
  if e.get('event')!='model_step':continue
  mapping=e.get('request_ids_to_seq_ids') or {}; matches=[ids[x] for x in mapping if x in ids]; decode=[x for x in e.get('groups',[]) if x['request_id'] in ids and not x['is_prompt']]
  if not matches or not decode:continue
  if len(matches)!=len(mapping) or len(decode)!=len(mapping):discard['mixed_phase']+=1;continue
  if len({(r['length'],r['batch'],r['wave'],r['warmup']) for r in matches})!=1:discard['mixed_wave']+=1;continue
  lens=e.get('seq_lens') or [];gpu=e.get('gpu_event_ms') or {};value=gpu.get('full_model_forward')
  if len(lens)!=len(mapping) or value is None:discard['missing_shape_or_forward']+=1;continue
  span=max(lens)-min(lens)
  if span>1:discard['context_span_gt_1']+=1;continue
  mean=int(sum(lens)/len(lens));binval=((mean+15)//16)*16;r=matches[0];k=(r['length'],len(mapping),binval,span>0);wave=(r['batch'],r['wave'],r['warmup']);groups[k][wave].append(float(value))
rows=[]
for key,waves in sorted(groups.items()):
 warm=[statistics.median(v) for (_,_,iswarm),v in waves.items() if iswarm];meas=[statistics.median(v) for (_,_,iswarm),v in waves.items() if not iswarm];rows.append({'input_tokens':key[0],'actual_batch':key[1],'rounded_mean_context':key[2],'mixed_context':int(key[3]),'warmup_waves':len(warm),'measured_waves':len(meas),'median_forward_ms':statistics.median(meas) if meas else '', 'eligible':int(len(warm)>=10 and len(meas)>=30)})
with (out/'forward-context-bins.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
summary=[]
for n in (1024,2048):
 for b in (1,2,3,4):
  sub=[x for x in rows if x['input_tokens']==n and x['actual_batch']==b];summary.append({'input_tokens':n,'actual_batch':b,'points':len(sub),'eligible':sum(x['eligible'] for x in sub),'mixed_eligible':sum(x['eligible'] and x['mixed_context'] for x in sub),'bins':sorted(set(x['rounded_mean_context'] for x in sub if x['eligible']))})
source={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in p.glob('compute-events-*.jsonl')};result={'status':'independent_candidate_not_frozen','inputs':len(req),'mapped_requests':len(ids),'source_hashes':source,'summary':summary,'discarded_steps':dict(discard),'contract':'average per-request sequence length truncated to integer, then ceil to 16-token blocks, matching predictor decode attention feature; group actual batch and mixed status; per-wave medians before across-wave median','limitations':['Full model forward CUDA event, not standalone attention cost; no CPU, router, logits, sampling or KV included','Polling/synchronization perturbs load; 128-token diagnostics may contain scheduler mixtures','Measured input token and mixed/uniform shape retained; no assertion that same rounded mean implies equivalent time','No extrapolation or imputation; 10 warmup and 30 distinct measured waves required per point','Different client requested batches can contribute separate waves; same physical wave counted once per shape; mixed and uniform remain separate','Candidate cannot be frozen until coupled fee/overlap semantics and missing shapes resolved']};(out/'manifest.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
