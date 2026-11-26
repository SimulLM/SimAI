import pathlib,json,csv,collections,hashlib,statistics
p=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/calibration-concurrent-independent-20261126');out=[];errors=[];summary=[]
for rep in range(3):
 rows=[json.loads(x) for x in (p/f'client-{rep}/requests.jsonl').read_text().splitlines()];ev=collections.defaultdict(lambda:collections.defaultdict(list))
 for line in (p/f'server-{rep}/router-events.jsonl').read_text().splitlines():
  x=json.loads(line);ev[x['request_id']][x['event']].append(x)
 waves=collections.defaultdict(list)
 for r in rows:waves[r['wave']].append(r)
 for w,rs in sorted(waves.items()):
  if len(rs)!=2 or set(x['index'] for x in rs)!={0,1}:errors.append({'repeat':rep,'wave':w,'error':'wave size'})
  if w+1 in waves and max(x['complete_ns'] for x in rs)>min(x['send_ns'] for x in waves[w+1]):errors.append({'repeat':rep,'wave':w,'error':'wave overlap'})
  for r in rs:
   names=['server_arrival','prefill_send','prefill_response','prefill_mapping','decode_send','decode_mapping','server_first_token','server_complete'];matched=ev[r.get('router_id')];missing=[n for n in names if len(matched[n])!=1];sha=hashlib.sha256(json.dumps(r['input_ids'],separators=(',',':')).encode()).hexdigest();issues=[]
   if missing:issues.append('missing '+str(missing))
   if sha!=r['input_sha256'] or len(r['input_ids'])!=512:issues.append('input')
   if r.get('status')!=200 or not r.get('done') or r.get('usage',{}).get('completion_tokens')!=64 or r.get('usage',{}).get('prompt_tokens')!=512:issues.append('status or usage')
   if not missing:
    t={n:matched[n][0]['timestamp_ns'] for n in names}
    if not(t['server_arrival']<=t['prefill_send']<=t['prefill_response']<=t['decode_send']<=t['server_first_token']<=t['server_complete']):issues.append('server order')
    if matched['decode_mapping'][0].get('backend_request_id')!=r.get('decode_id'):issues.append('decode id')
    r['server_e2e_ms']=(t['server_complete']-t['server_arrival'])/1e6
   if issues:errors.append({'repeat':rep,'wave':w,'index':r['index'],'issues':issues})
   out.append({'repeat':rep,'wave':w,'index':r['index'],'warmup':r['warmup'],'router_id':r.get('router_id'),'input_sha256':r['input_sha256'],'status':r.get('status'),'server_e2e_ms':r.get('server_e2e_ms'),'client_e2e_ms':(r['complete_ns']-r['send_ns'])/1e6,'issues':'|'.join(issues)})
 meas=[x for x in out if x['repeat']==rep and not x['warmup']];tel=p/f'server-{rep}-telemetry.csv';summary.append({'repeat':rep,'measured':len(meas),'median_server_e2e_ms':statistics.median(x['server_e2e_ms'] for x in meas if x['server_e2e_ms'] is not None) if meas else None,'telemetry_rows':sum(1 for _ in tel.open())-1 if tel.exists() else 0,'resource_after':(p/f'server-{rep}-resource-after.csv').read_text().strip()})
with (p/'audit-requests.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=out[0]);w.writeheader();w.writerows(out)
res={'status':'concurrent_repeats_recorded' if len(out)==108 and not errors and all(x['measured']==32 and x['telemetry_rows']>0 for x in summary) else 'failed','summary':summary,'errors':errors,'unique_input_hashes':len(set(x['input_sha256'] for x in out)),'limitations':['Separate service restart and completion of each client wave do not prove internal KV cleanup after warmup','server completion is router stream completion, not GPU completion','telemetry is sampled at 1 second with wall timestamps; short GPU events are not resolved','fee compatibility and actual service scheduling remain separate, no validation completion times used to fit fees']};(p/'audit.json').write_text(json.dumps(res,indent=2)+'\n');print(json.dumps(res,indent=2));raise SystemExit(0 if res['status']=='concurrent_repeats_recorded' else 1)
