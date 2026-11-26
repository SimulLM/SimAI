"""Compare submission and observed consumer-step order within measured waves."""
import collections,csv,itertools,json,pathlib
root=pathlib.Path(__file__).resolve().parent
source=root.parent/'pd-flow-boundary-20261126'/'derived-boundaries.csv'
rows=[r for r in csv.DictReader(source.open()) if r['warmup'].lower()=='false']
waves=collections.defaultdict(list)
for r in rows:waves[(int(r['input_tokens']),int(r['requested_batch']),int(r['wave']))].append(r)
result=collections.defaultdict(collections.Counter)
for (length,concurrency,wave),items in waves.items():
 if len(items)!=concurrency:raise ValueError(f'incomplete wave {(length,concurrency,wave)}')
 for a,b in itertools.combinations(items,2):
  submit=int(a['decode_submit_ns'])-int(b['decode_submit_ns'])
  step=int(a['decode_kv_step_host_start_ns'])-int(b['decode_kv_step_host_start_ns'])
  key=(length,concurrency)
  if submit==0:label='submission_tie'
  elif step==0:label='same_consumer_step_time'
  elif submit*step>0:label='same_order'
  else:label='inversion'
  result[key][label]+=1
summary={'scope':'Instrumented 8-token diagnostic, request pairs within waves only; equal step timestamps are shared step observations, not an ordering','groups':[{'input_tokens':k[0],'requested_concurrency':k[1],'pair_counts':dict(v)} for k,v in sorted(result.items())]}
(root/'wave-order.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
