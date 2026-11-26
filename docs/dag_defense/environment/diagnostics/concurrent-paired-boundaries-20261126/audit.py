import collections,csv,hashlib,json,math,pathlib,statistics,tarfile
out=pathlib.Path(__file__).parent
src=pathlib.Path('/root/autodl-tmp/SimAI-handoff/docs/dag_defense/environment/diagnostics/pd-kv-ready-bound-20261126/raw.tar.gz')
with tarfile.open(src) as t:
 def read(name):return [json.loads(x) for x in t.extractfile(name)]
 req=read('coverage/requests.jsonl');routes={x['decode_id']:x for x in read('router-events.jsonl') if x.get('decode_id')}; events={}
 for name in ('compute-events-86396.jsonl','compute-events-86401.jsonl'):
  for e in read(name):
   h=e.get('host_intervals',{})
   if e.get('event')=='model_step' and 'kv_ready_sync_ns' in h:
    for rid in e['request_ids_to_seq_ids']: assert rid not in events;events[rid]=e
 steps={}
 for r in req:
  assert r['status']==200 and r['usage']['prompt_tokens']==r['length'] and r['usage']['completion_tokens']==8
  rid=routes[r['backend_request_id']]['decode_id']+'-0';e=events[rid];h=e['host_intervals'];start=h['recv_kv_caches_and_hidden_states'][0];sync=h['kv_ready_sync_ns'][1];end=e['host_after_sync_ns'];assert e['host_start_ns']<=start<=sync<=end and h['kv_bypass']
  key=(e['pid'],e['host_start_ns']);row=steps.setdefault(key,{'input_tokens':r['length'],'requested_concurrency':r['batch'],'wave':r['wave'],'warmup':r['warmup'],'pid':e['pid'],'step_start_ns':key[1],'recv_start_ns':start,'kv_sync_ns':sync,'step_return_ns':end,'step_ids':sorted(e['request_ids_to_seq_ids']),'mapped_ids':[]})
  assert (row['input_tokens'],row['requested_concurrency'],row['wave'],row['warmup'])==(r['length'],r['batch'],r['wave'],r['warmup']);row['mapped_ids'].append(rid)
rows=[];groups=collections.defaultdict(list)
for row in steps.values():
 row['mapped_ids'].sort();assert row['mapped_ids']==row['step_ids'];row['actual_batch']=len(row['mapped_ids']);row['receive_to_sync_ms']=(row['kv_sync_ns']-row['recv_start_ns'])/1e6;row['post_sync_ms']=(row['step_return_ns']-row['kv_sync_ns'])/1e6;row['combined_ms']=(row['step_return_ns']-row['recv_start_ns'])/1e6
 assert abs(row['receive_to_sync_ms']+row['post_sync_ms']-row['combined_ms'])<1e-9
 rows.append(row);groups[(row['input_tokens'],row['requested_concurrency'],row['actual_batch'],row['warmup'])].append(row)
summaries=[]
for (n,requested,batch,warm),v in sorted(groups.items()):
 waves=collections.defaultdict(list)
 for r in v:waves[r['wave']].append(r)
 # Median per wave keeps multiple steps from being treated as independent waves.
 agg={k:sorted(statistics.median(r[k] for r in rs) for rs in waves.values()) for k in ('receive_to_sync_ms','post_sync_ms','combined_ms')}
 row={'input_tokens':n,'requested_concurrency':requested,'actual_batch':batch,'warmup':warm,'steps':len(v),'waves':len(waves)}
 for k,values in agg.items():row[k+'_median']=statistics.median(values);row[k+'_min']=min(values);row[k+'_p95']=values[math.ceil(.95*len(values))-1];row[k+'_max']=max(values)
 summaries.append(row)
with (out/'steps.jsonl').open('w') as f:
 for row in rows:f.write(json.dumps(row,sort_keys=True)+'\n')
with (out/'summary.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=summaries[0]);w.writeheader();w.writerows(summaries)
(out/'audit.json').write_text(json.dumps({'source_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'requests':len(req),'steps':len(rows),'all_request_ids_reconciled':True,'step_subintervals_nonoverlapping':True,'notes':['host boundaries not exact GPU transfer completion','per-tensor sync perturbs scheduling','same service session','grouped by requested concurrency and actual batch; multiple steps per wave aggregated','cannot add combined interval to subintervals or KV-install fee','8 outputs; no production E2E claim']},indent=2)+'\n')
# Within the same measured client wave, compare inclusive connector intervals.
bywave=collections.defaultdict(list)
for r in rows:
 if not r['warmup']:bywave[(r['input_tokens'],r['requested_concurrency'],r['wave'])].append(r)
overlap=[]
for (n,conc,wave),rr in sorted(bywave.items()):
 intervals=sorted((r['recv_start_ns'],r['kv_sync_ns']) for r in rr);summed=sum(b-a for a,b in intervals);merged=[]
 for a,b in intervals:
  if merged and a<=merged[-1][1]:merged[-1]=(merged[-1][0],max(b,merged[-1][1]))
  else:merged.append((a,b))
 union=sum(b-a for a,b in merged)
 overlap.append({'input_tokens':n,'requested_concurrency':conc,'wave':wave,'steps':len(rr),'receive_sum_ms':summed/1e6,'receive_union_ms':union/1e6,'double_count_if_summed_ms':(summed-union)/1e6})
with (out/'wave-overlap.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=overlap[0]);w.writeheader();w.writerows(overlap)
for key in sorted({(r['input_tokens'],r['requested_concurrency']) for r in overlap}):
 vals=[r for r in overlap if (r['input_tokens'],r['requested_concurrency'])==key];print(key,'waves',len(vals),'overlap_waves',sum(r['double_count_if_summed_ms']>0 for r in vals),'median_overlap_ms',statistics.median(r['double_count_if_summed_ms'] for r in vals),'max_overlap_ms',max(r['double_count_if_summed_ms'] for r in vals))
