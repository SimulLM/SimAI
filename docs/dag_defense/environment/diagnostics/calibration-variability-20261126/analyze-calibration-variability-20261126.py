import pathlib,json,csv,statistics,collections
root=pathlib.Path('/root/autodl-tmp/dag-handoff/runs');out=root/'calibration-variability-20261126';out.mkdir(exist_ok=False);allrows=[];errors=[]
for mode in ('serial','concurrent'):
 p=root/f'calibration-{mode}-independent-20261126'
 for rep in range(3):
  ev=collections.defaultdict(dict)
  for line in (p/f'server-{rep}/router-events.jsonl').read_text().splitlines():
   x=json.loads(line);ev[x['request_id']][x['event']]=x
  for line in (p/f'client-{rep}/requests.jsonl').read_text().splitlines():
   r=json.loads(line)
   if r['warmup']:continue
   try:
    e=ev[r['router_id']];t=lambda n:e[n]['timestamp_ns'];arrival=t('server_arrival');send=t('prefill_send');pdone=t('prefill_response');decode=t('decode_send');first=t('server_first_token');done=t('server_complete')
    row={'mode':mode,'repeat':rep,'index':r.get('index'),'wave':r.get('wave',r.get('index')),'router_id':r['router_id'],'server_e2e_ms':(done-arrival)/1e6,'prefill_response_ms':(pdone-send)/1e6,'router_pre_to_decode_ms':(decode-pdone)/1e6,'decode_to_first_ms':(first-decode)/1e6,'first_to_finish_ms':(done-first)/1e6,'client_e2e_ms':(r['complete_ns']-r['send_ns'])/1e6};allrows.append(row)
   except Exception as x:errors.append({'mode':mode,'repeat':rep,'id':r.get('router_id'),'error':repr(x)})
with (out/'phase-intervals.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=allrows[0]);w.writeheader();w.writerows(allrows)
fields=['server_e2e_ms','prefill_response_ms','router_pre_to_decode_ms','decode_to_first_ms','first_to_finish_ms'];summary=[]
for mode in ('serial','concurrent'):
 for rep in range(3):
  rows=sorted([r for r in allrows if r['mode']==mode and r['repeat']==rep],key=lambda r:(r['wave'],r['index'])); s={'mode':mode,'repeat':rep,'n':len(rows)}
  for k in fields:
   vals=sorted(x[k] for x in rows);s[k]={'median':statistics.median(vals),'min':vals[0],'max':vals[-1]}
  summary.append(s)
res={'rows':len(allrows),'errors':errors,'summary':summary,'limitations':['Router host intervals include service queueing, network and CPU work; they do not identify GPU kernel durations or isolate causal bottlenecks.','First token and completion are router stream observations, not GPU timestamps.','Different input arrays across runs; no frozen costs or validation outcomes used.','Concurrent requests share batches and are not independent samples.']};(out/'summary.json').write_text(json.dumps(res,indent=2)+'\n');print(json.dumps(res,indent=2))
