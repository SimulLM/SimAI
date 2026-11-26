"""Audit layer-16 event samples on matched batch-3 context bins, not request E2E."""
import collections,csv,hashlib,json,pathlib,statistics,sys
runs=[pathlib.Path(p) for p in sys.argv[1:-1]]; out=pathlib.Path(sys.argv[-1]);out.mkdir(exist_ok=False)
components=('attn_pre_proj','attn_rope','attn_post_proj','mlp_up_proj','mlp_act','mlp_down_proj','input_layernorm','post_attention_layernorm','attention_combined','full_model_forward')
groups=collections.defaultdict(lambda:collections.defaultdict(lambda:collections.defaultdict(list)));sources={};discard=collections.Counter()
for p in runs:
 if (p/'exit').read_text().strip()!='0':raise ValueError('unsuccessful input run')
 def read(f):
  sources[str(f)]=hashlib.sha256(f.read_bytes()).hexdigest()
  return [json.loads(x) for x in f.read_text().splitlines()]
 req=read(p/'client/requests.jsonl');routes={x['decode_id']:x for x in read(p/'router-events.jsonl') if x.get('decode_id')}; ids={routes[x['backend_request_id']]['decode_id']+'-0':x for x in req if x.get('backend_request_id') in routes}
 if len(ids)!=len(req):raise ValueError('mapping incomplete')
 for f in sorted(p.glob('compute-events-*.jsonl')):
  for e in read(f):
   if e.get('event')!='model_step':continue
   mapping=e.get('request_ids_to_seq_ids') or {};matches=[ids[x] for x in mapping if x in ids and ids[x]['length']==1024];decode=[x for x in e.get('groups',[]) if x['request_id'] in ids and ids[x['request_id']]['length']==1024 and not x['is_prompt']]
   if not matches or not decode:continue
   if len(mapping)!=3 or len(matches)!=3 or len(decode)!=3:continue
   if len({(r['length'],r['batch'],r['wave'],r['warmup']) for r in matches})!=1:discard['mixed_wave']+=1;continue
   lens=e.get('seq_lens') or []; gpu=e.get('gpu_event_ms') or {}
   if len(lens)!=3 or any(gpu.get(k) is None for k in components):discard['missing_component_or_shape']+=1;continue
   span=max(lens)-min(lens)
   if span>1:discard['context_span_gt_1']+=1;continue
   context=((int(sum(lens)/len(lens))+15)//16)*16; r=matches[0]; wave=(str(p),r['batch'],r['wave'],r['warmup']);key=(context,int(span>0))
   for k in components:groups[key][wave][k].append(float(gpu[k]))
rows=[]
for (context,mixed),waves in sorted(groups.items()):
 warm=[x for x in waves if x[3]]; measured=[x for x in waves if not x[3]]
 for k in components:
  samples=[statistics.median(waves[x][k]) for x in measured]
  rows.append({'context_bin':context,'mixed_context':mixed,'component':k,'warmup_waves':len(warm),'measured_waves':len(measured),'median_ms':statistics.median(samples) if samples else None,'eligible':len(warm)>=10 and len(measured)>=30})
with (out/'components.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
result={'rows':len(rows),'sources':sources,'discarded':dict(discard),'contract':'Each cell retains mixed/uniform separation and independent wave identity. Per-wave component medians summarized across measured waves. Layer 16 except full_model_forward. Components are not summed; GPU intervals may overlap. No CPU/KV/router costs or service E2E.'}
(out/'manifest.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
