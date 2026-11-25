import argparse,collections,csv,glob,json,statistics
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--events-dir',type=Path,required=True);p.add_argument('--clients',type=Path,nargs='+',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
fields=['input_layernorm','attn_pre_proj','attn_rope','attention_combined','attn_post_proj','post_attention_layernorm','mlp_up_proj','mlp_act','mlp_down_proj','embedding','final_norm','logits_processor']
requests={}; expected=0
for directory in a.clients:
 spec=json.loads((directory/'client-spec.json').read_text());rows=[json.loads(x) for x in (directory/'client-requests.jsonl').read_text().splitlines()]
 assert (directory/'client-exit-code').read_text().strip()=='0'; target=sum(spec['warmup_waves']+spec['measured_waves'] for _ in spec['lengths'] for b in spec['batches'] for _ in range(b)); assert len(rows)==target,(directory,len(rows),target)
 for row in rows:
  assert row['status']==200 and 'error' not in row and row['usage']['prompt_tokens']==row['length'] and row['usage']['completion_tokens']==2 and row['finish_reason']=='length'
  rid=row['request_id']+'-0'; assert rid not in requests;row['source']=directory.name;requests[rid]=row
 expected+=target
steps=[];installed=[]
for path in glob.glob(str(a.events_dir/'compute-events-*.jsonl')):
 for line in open(path):
  event=json.loads(line)
  if event['event']=='hooks_installed':installed.append(event);continue
  if event['event']=='model_step':steps.append(event)
assert len(installed)==1 and installed[0]['rope_theta']==10000.0 and installed[0]['rope_scaling'] is None
steps.sort(key=lambda e:e['host_start_ns']); seen=collections.Counter(); warm=collections.Counter(); measured=collections.defaultdict(list); mixed=[]; unmapped=0; samples=[]
for e in steps:
 groups=e['groups'];ids=[g['request_id'] for g in groups]; rs=[requests.get(i) for i in ids]
 if any(x is None for x in rs):unmapped+=1;continue
 assert len(e['seq_lens'])==len(groups) and len(e['query_lens'])==len(groups)
 for rid,g in zip(ids,groups):seen[(rid,g['is_prompt'])]+=1
 if len({(x['source'],x['length'],x['batch'],x['wave'],x['warmup']) for x in rs})!=1 or len({g['is_prompt'] for g in groups})!=1: mixed.append(e);continue
 assert set(e['gpu_event_ms'])==set(fields) and all(e['gpu_event_ms'][k]>=0 for k in fields)
 row=rs[0]; phase='prefill' if groups[0]['is_prompt'] else 'decode';actual=len(groups);key=(phase,row['length'],actual)
 assert all(n==row['length'] for n in e['seq_lens']) if phase=='prefill' else all(n==row['length']+1 for n in e['seq_lens'])
 if row['warmup']:warm[key]+=1;eligible=False
 else:
  eligible=warm[key]>=10
  if eligible:measured[key].append(e['gpu_event_ms'])
 samples.append(dict(phase=phase,input_tokens=row['length'],actual_batch=actual,requested_batch=row['batch'],source=row['source'],wave=row['wave'],warmup=int(row['warmup']),eligible=int(eligible),request_ids='|'.join(ids),host_start_ns=e['host_start_ns'],**e['gpu_event_ms']))
missing=[rid for rid in requests if seen[(rid,True)]!=1 or seen[(rid,False)]!=1]
assert not missing and not mixed,(len(missing),len(mixed))
summary=[]
for key,values in sorted(measured.items()):
 phase,n,b=key; entry={'phase':phase,'input_tokens':n,'decode_context_tokens':n+1 if phase=='decode' else '', 'actual_batch':b,'warmups_seen':warm[key],'eligible_samples':len(values),'at_least_30':len(values)>=30}
 for f in fields:entry[f+'_median_ms']=statistics.median(x[f] for x in values)
 summary.append(entry)
for name,rows in [('samples.csv',samples),('summary.csv',summary)]:
 with (a.output/name).open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
coverage={'requests':expected,'matched_requests':len(requests),'unmapped_steps':unmapped,'mixed_steps':len(mixed),'missing_or_repeated_phase_requests':len(missing),'samples_recorded':len(samples),'eligible_shape_count':sum(x['at_least_30'] for x in summary),'partial_shape_count':sum(not x['at_least_30'] for x in summary),'rope_theta':installed[0]['rope_theta'],'rope_scaling':installed[0]['rope_scaling'],'method':'diagnostic eager, selected layer 16, CUDA events, synchronization after each model step'}
(a.output/'coverage.json').write_text(json.dumps(coverage,indent=2)+'\n');print(json.dumps(coverage,indent=2))
