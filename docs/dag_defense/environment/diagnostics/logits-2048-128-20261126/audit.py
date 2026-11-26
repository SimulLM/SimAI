import collections,csv,json,pathlib,statistics
p=pathlib.Path(__file__).parent
assert (p/'exit').read_text().strip()=='0'
requests=[json.loads(l) for l in (p/'client/requests.jsonl').open()]
assert len(requests)==160 and all(r['status']==200 and r['usage']['prompt_tokens']==2048 and r['usage']['completion_tokens']==128 for r in requests)
lookup={r['backend_request_id']+'-0':r for r in requests};assert len(lookup)==160
waves=collections.defaultdict(list);seen=set();per_request=collections.Counter();events=0
for f in (p/'service').glob('compute-events-*.jsonl'):
 for line in f.open():
  e=json.loads(line)
  if e.get('event')!='model_step':continue
  groups=e.get('groups',[]);members=[g['request_id'] for g in groups if g['request_id'] in lookup and not g['is_prompt']]
  if not members:continue
  assert len(members)==len(groups)==len(e['request_ids_to_seq_ids'])
  src=[lookup[i] for i in members];meta={(r['wave'],r['warmup']) for r in src};assert len(meta)==1,meta
  wave,warmup=next(iter(meta));key=(e['pid'],e['host_start_ns']);assert key not in seen;seen.add(key)
  for rid in members:per_request[rid]+=1
  assert len(e['seq_lens'])==len(members) and 'logits_gpu' in e['gpu_event_ms']
  contexts=[int(x) for x in e['seq_lens']];max_context=max(contexts);bin_index=min((max_context-2049)//32,3);assert 0<=bin_index<=3,(contexts,bin_index)
  waves[(wave,warmup,len(members),bin_index)].append(e['gpu_event_ms']['logits_gpu']);events+=1
assert set(per_request)==set(lookup) and set(per_request.values())=={127},collections.Counter(per_request.values())
rows=[]
for (wave,warmup,batch,bin_index),vals in sorted(waves.items()):rows.append({'wave':wave,'warmup':warmup,'actual_batch':batch,'context_bin':bin_index,'steps':len(vals),'median_logits_ms':statistics.median(vals)})
with (p/'wave-logits.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
groups=collections.defaultdict(list)
for row in rows:groups[(row['actual_batch'],row['context_bin'],row['warmup'])].append(row['median_logits_ms'])
coverage=[]
for batch in range(1,5):
 for bin_index in range(4):
  warm=groups[(batch,bin_index,True)];values=groups[(batch,bin_index,False)]
  coverage.append({'actual_batch':batch,'context_bin':bin_index,'warmup_waves':len(warm),'measured_waves':len(values),'median_ms':statistics.median(values) if values else None,'meets_10_30':len(warm)>=10 and len(values)>=30})
result={'requests':len(requests),'warmup_waves':10,'measured_waves':30,'deduplicated_steps':events,'coverage':coverage,'limitations':['Detailed instrumentation adds synchronization and is not formal E2E','Different actual batch groups can appear within a wave; contexts within a batch need not be equal','One service session, no independent restart variability','Host sampler and GPU event intervals can overlap; no additive cost claim']}
(p/'audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
