import json,csv,pathlib,collections,statistics,sys,math
p=pathlib.Path(sys.argv[1]); read=lambda f:[json.loads(x) for x in f.read_text().splitlines()]
req=read(p/'client/requests.jsonl');rt={r['decode_id']:r for r in read(p/'router-events.jsonl') if r.get('decode_id')};idx={rt[r['backend_request_id']]['decode_id']+'-0':r for r in req if r.get('backend_request_id') in rt}; counts=collections.Counter(); waves=collections.defaultdict(set);spans=collections.defaultdict(list);hist=collections.Counter(); dropped=collections.Counter()
for f in p.glob('compute-events-*.jsonl'):
 with f.open() as stream:
  for line in stream:
   e=json.loads(line)
   if e.get('event')!='model_step':continue
   ids=e.get('request_ids_to_seq_ids') or {}; relevant=[idx[i] for i in ids if i in idx];g=[x for x in e.get('groups',[]) if x['request_id'] in idx and not x['is_prompt']]
   if not relevant or not g:continue
   if len(relevant)!=len(ids) or len(g)!=len(ids):dropped['mixed_phase']+=1;continue
   if len({(r['length'],r['batch'],r['wave'],r['warmup']) for r in relevant})!=1:dropped['mixed_wave']+=1;continue
   lens=e.get('seq_lens') or []
   if len(lens)!=len(ids):dropped['length_count']+=1;continue
   r=relevant[0];n=r['length'];b=len(ids);span=max(lens)-min(lens);mean=sum(lens)/len(lens)-n;warm=r['warmup'];key=(n,r['batch'],b,'mixed' if span else 'uniform',warm)
   counts[key]+=1;waves[key].add(r['wave']);spans[key].append(span);hist[(n,b,math.floor(mean),warm)]+=1
summary=[]
for k,v in sorted(counts.items()):
 a=spans[k];summary.append({'input_tokens':k[0],'requested_concurrency':k[1],'actual_batch':k[2],'context_type':k[3],'warmup':k[4],'steps':v,'distinct_waves':len(waves[k]),'median_context_span_tokens':statistics.median(a),'p95_context_span_tokens':sorted(a)[math.ceil(.95*len(a))-1],'max_context_span_tokens':max(a)})
with (p/'mixed-context-summary.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=summary[0]);w.writeheader();w.writerows(summary)
out={'status':'diagnostic','rows':summary,'dropped':dict(dropped),'note':'Context span within one actual batch; event counts share waves and are not independent. Average context alone does not prove equivalence of mixed and uniform attention work. GPU diagnostic synchronization perturbs scheduler.'};(p/'mixed-context-audit.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({'rows':[r for r in summary if not r['warmup'] and r['actual_batch']>1], 'dropped':dict(dropped)},indent=2))
