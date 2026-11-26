import collections,json,pathlib,statistics,hashlib,math
p=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/first-token-batch4-repeat-20261126');o=pathlib.Path(__file__).parent
assert (p/'exit').read_text().strip()=='0';req=[json.loads(x) for x in (p/'coverage/requests.jsonl').read_text().splitlines()];assert len(req)==168 and all(r['status']==200 and r['usage']['prompt_tokens']==1024 and r['usage']['completion_tokens']==8 for r in req)
routes={r['decode_id']:r for r in (json.loads(x) for x in (p/'router-events.jsonl').read_text().splitlines()) if r.get('decode_id')};ev={}
for f in p.glob('compute-events-*.jsonl'):
 for line in f.open():
  x=json.loads(line);h=x.get('host_intervals',{})
  if x.get('event')=='model_step' and 'kv_ready_sync_ns' in h:
   for rid in x['request_ids_to_seq_ids']:assert rid not in ev;ev[rid]=x
steps={}
for r in req:
 rid=routes[r['backend_request_id']]['decode_id']+'-0';e=ev[rid];h=e['host_intervals'];start=h['kv_ready_sync_ns'][1];end=e['host_after_sync_ns'];assert h['kv_bypass'] and start<=end
 key=(e['pid'],e['host_start_ns']);row=steps.setdefault(key,{'wave':r['wave'],'warmup':r['warmup'],'ids':sorted(e['request_ids_to_seq_ids']),'mapped':[],'post_sync_host_ms':(end-start)/1e6});assert row['wave']==r['wave'] and row['warmup']==r['warmup'];row['mapped'].append(rid)
for row in steps.values():row['mapped'].sort();assert row['mapped']==row['ids'];row['batch']=len(row['ids'])
c=collections.Counter((x['warmup'],x['batch']) for x in steps.values());target=[x for x in steps.values() if x['batch']==4 and not x['warmup']];warm=[x for x in steps.values() if x['batch']==4 and x['warmup']];assert len({x['wave'] for x in target})==len(target) and len({x['wave'] for x in warm})==len(warm)
v=sorted(x['post_sync_host_ms'] for x in target);res={'status':'qualified' if len(warm)>=10 and len(v)>=30 else 'insufficient','requests':len(req),'steps':len(steps),'batch_counts':{str(k):v for k,v in c.items()},'batch4_warmup_waves':len(warm),'batch4_measured_waves':len(v),'median_ms':statistics.median(v) if v else None,'p95_ms':v[math.ceil(.95*len(v))-1] if v else None,'min_ms':min(v) if v else None,'max_ms':max(v) if v else None,'sources':{str(x):hashlib.sha256(x.read_bytes()).hexdigest() for x in [p/'coverage/requests.jsonl',p/'router-events.jsonl',*p.glob('compute-events-*.jsonl')]},'limitations':['diagnostic holds decode until four prefill responses; not natural arrival scheduling','per-tensor synchronization perturbs measurement','one service session','8 output tokens, not 128','host interval contains logits sampler and final synchronization; no GPU exclusivity claim']}
(o/'audit.json').write_text(json.dumps(res,indent=2)+'\n');(o/'steps.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in steps.values()));print(json.dumps(res,indent=2))
