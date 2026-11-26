import pathlib,json,csv,collections,hashlib,statistics
p=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/calibration-serial-independent-20261126');allrows=[];errors=[];summary=[]
for rep in range(3):
 c=p/f'client-{rep}/requests.jsonl';e=p/f'server-{rep}/router-events.jsonl';rows=[json.loads(x) for x in c.read_text().splitlines()];ev=collections.defaultdict(lambda:collections.defaultdict(list))
 for line in e.read_text().splitlines():
  x=json.loads(line);ev[x['request_id']][x['event']].append(x)
 if len(rows)!=36:errors.append({'repeat':rep,'error':'row count','count':len(rows)})
 for i,r in enumerate(rows):
  names=['server_arrival','prefill_send','prefill_response','prefill_mapping','decode_send','decode_mapping','server_first_token','server_complete'];matched=ev[r.get('router_id')];missing=[n for n in names if len(matched[n])!=1];sha=hashlib.sha256(json.dumps(r['input_ids'],separators=(',',':')).encode()).hexdigest();issues=[]
  if missing:issues.append('missing '+str(missing))
  if sha!=r['input_sha256'] or len(r['input_ids'])!=512:issues.append('input')
  if r.get('status')!=200 or not r.get('done') or r.get('usage',{}).get('completion_tokens')!=64 or r.get('usage',{}).get('prompt_tokens')!=512:issues.append('status or usage')
  if i and rows[i-1]['complete_ns']>r['send_ns']:issues.append('client overlap')
  if not missing:
   t={n:matched[n][0]['timestamp_ns'] for n in names}
   if not(t['server_arrival']<=t['prefill_send']<=t['prefill_response']<=t['decode_send']<=t['server_first_token']<=t['server_complete']):issues.append('server event order')
   if matched['decode_mapping'][0].get('backend_request_id')!=r.get('decode_id'):issues.append('decode id')
   r['server_e2e_ms']=(t['server_complete']-t['server_arrival'])/1e6
  if issues:errors.append({'repeat':rep,'index':r['index'],'issues':issues})
  allrows.append({'repeat':rep,'index':r['index'],'warmup':r['warmup'],'router_id':r.get('router_id'),'status':r.get('status'),'input_sha256':r['input_sha256'],'server_e2e_ms':r.get('server_e2e_ms'),'client_e2e_ms':(r['complete_ns']-r['send_ns'])/1e6,'issues':'|'.join(issues)})
 meas=[x for x in allrows if x['repeat']==rep and not x['warmup']];summary.append({'repeat':rep,'measured':len(meas),'median_server_e2e_ms':statistics.median(x['server_e2e_ms'] for x in meas if x['server_e2e_ms'] is not None) if meas else None,'server_launch_separate':(p/f'server-{rep}/ready').exists(),'resource_after':(p/f'server-{rep}-resource-after.csv').read_text().strip()})
with (p/'audit-requests.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=allrows[0]);w.writeheader();w.writerows(allrows)
res={'status':'serial_repeats_recorded' if len(allrows)==108 and not errors and all(x['measured']==32 for x in summary) else 'failed','summary':summary,'errors':errors,'unique_input_hashes':len(set(x['input_sha256'] for x in allrows)),'limitations':['Service restart and sequential completion support no prior request backlog; no direct proof of internal KV clearing after warmup','server completion is router stream completion and not GPU completion','only serial calibration; concurrent calibration provenance and fee compatibility remain separate','no validation completion times used to fit fees']};(p/'audit.json').write_text(json.dumps(res,indent=2)+'\n');print(json.dumps(res,indent=2));raise SystemExit(0 if res['status']=='serial_repeats_recorded' else 1)
