import json,collections,statistics,pathlib,csv
p=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/logits-2048-128-20261126');out=pathlib.Path(__file__).parent
req=[json.loads(x) for x in (p/'client/requests.jsonl').open()];ids={x['backend_request_id']+'-0':x for x in req};assert len(ids)==160
waves=collections.defaultdict(list);seen=set();steps=collections.Counter()
for f in (p/'service').glob('compute-events-*.jsonl'):
 for l in f.open():
  e=json.loads(l);g=e.get('groups',[])
  if e.get('event')!='model_step' or not g or not all(x['request_id'] in ids and not x['is_prompt'] for x in g):continue
  m=[ids[x['request_id']] for x in g];wavewarm={(x['wave'],x['warmup']) for x in m};assert len(wavewarm)==1
  lens=e['seq_lens'];assert len(lens)==len(g);identity=(e['pid'],e['host_start_ns']);assert identity not in seen;seen.add(identity)
  spread=max(lens)-min(lens);kind='uniform' if spread==0 else 'mixed';b=len(lens);bin_no=min((max(lens)-2049)//32,3);assert 0<=bin_no<=3
  wave,warm=next(iter(wavewarm));waves[(b,kind,bin_no,wave,warm)].append(e['gpu_event_ms']['logits_gpu']);steps[(b,kind,warm)]+=1
rows=[]
for b in range(1,5):
 for kind in ('uniform','mixed'):
  for bin_no in range(4):
   warm=[v for (bb,kk,nn,w,ww),v in waves.items() if (bb,kk,nn,ww)==(b,kind,bin_no,True)]
   measured=[v for (bb,kk,nn,w,ww),v in waves.items() if (bb,kk,nn,ww)==(b,kind,bin_no,False)]
   rows.append({'actual_batch':b,'composition':kind,'context_bin':bin_no,'warmup_waves':len(warm),'measured_waves':len(measured),'median_ms':statistics.median(statistics.median(x) for x in measured) if measured else None,'meets_10_30':len(warm)>=10 and len(measured)>=30})
with (out/'coverage.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
summary={'total_distinct_steps':len(seen),'steps':[{'actual_batch':b,'composition':k,'warmup':w,'count':n} for (b,k,w),n in sorted(steps.items())],'coverage':rows,'limitations':['Context bin uses maximum batch sequence length','One instrumented session; separate requests may share a wave','Not an additive fee or formal E2E']};(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print('total',len(seen));print('batch4',[(r['composition'],r['context_bin'],r['warmup_waves'],r['measured_waves']) for r in rows if r['actual_batch']==4])
