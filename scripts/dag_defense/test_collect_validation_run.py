"""Test only against an isolated synthetic local service."""
import asyncio,json,pathlib,tempfile,hashlib
from aiohttp import web
from collect_validation_run import run_case,preflight
from reconcile_validation_run import reconcile
async def main():
 async def handle(req):
  body=await req.json();i=body['prompt'][1];mode=body['model'];assert req.headers['X-Experiment-Client-ID']==str(i)
  if mode=='fail' and i==1:return web.Response(status=503,text='injected failure')
  if mode=='timeout' and i==2:await asyncio.sleep(.35)
  usage={'prompt_tokens':4,'completion_tokens':128};payload='data: '+json.dumps({'id':'fake-'+str(i),'usage':usage})+'\n\ndata: [DONE]\n\n'
  return web.Response(text=payload,content_type='text/event-stream',headers={'X-Experiment-Request-ID':'fixture-'+str(i)})
 app=web.Application();app.router.add_post('/v1/completions',handle);runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start();port=site._server.sockets[0].getsockname()[1]
 try:
  with tempfile.TemporaryDirectory() as td:
   root=pathlib.Path(td);rows=[{'run_id':'fixture','request_id':str(i),'input_id':'input'+str(i),'input_sha256':'fixture','wave':i//2,'input_ids':[1,i]} for i in range(32)];spec={'run_id':'fixture','input_tokens':4,'concurrency':2,'requests':32};results={}
   for mode,expected in [('success',{'success':32,'failed':0,'timeout':0,'not_submitted':0}),('fail',{'success':1,'failed':1,'timeout':0,'not_submitted':30}),('timeout',{'success':3,'failed':0,'timeout':1,'not_submitted':28})]:
    await run_case(spec,rows,root/mode,f'http://127.0.0.1:{port}/v1/completions',mode,.15)
    records=[json.loads(x) for x in (root/mode/'client-events.jsonl').read_text().splitlines()];counts={k:sum(x['status']==k for x in records) for k in expected};assert counts==expected,(mode,counts);assert len({x['request_id'] for x in records})==32;events=[json.loads(x) for x in (root/mode/'wave-events.jsonl').read_text().splitlines()];assert all(events[2*i]['event']=='scheduled' and events[2*i+1]['event']=='complete' for i in range(len(events)//2));results[mode]={'counts':counts,'waves_sent':len(events)//2}
   inputs=root/'fixture-input.jsonl';inputs.write_text(''.join(json.dumps(r)+'\n' for r in rows));router=root/'fixture-router.jsonl';server=[]
   for i in range(32):
    for name,t in [('server_arrival',100),('prefill_send',110),('prefill_response',120),('prefill_mapping',130),('decode_send',140),('decode_mapping',150),('server_first_token',160),('server_final_choice_observed',190),('server_complete',200)]:
     item={'request_id':'fixture-'+str(i),'event':name,'timestamp_ns':t,'clock_id':'CLOCK_MONOTONIC'}
     if name=='server_arrival':item['client_request_id']=str(i)
     if name=='decode_mapping':item['backend_request_id']='fake-'+str(i)
     if name=='prefill_response':item['status']=200
     if name=='server_final_choice_observed':item.update(finish_reasons=['length'],completion_tokens=128)
     if name=='server_complete':item['usage']={'prompt_tokens':4,'completion_tokens':128}
     server.append(item)
   router.write_text(''.join(json.dumps(r)+'\n' for r in server));good=reconcile(inputs,root/'success/client-events.jsonl',router,root/'reconciled-good');assert good['status']=='complete',good
   for mode in ('missing','duplicate','bad_reason','bad_count','order'):
    revised=[dict(x) for x in server];target=next(x for x in revised if x['request_id']=='fixture-0' and x['event']=='server_final_choice_observed')
    if mode=='missing':revised.remove(target)
    elif mode=='duplicate':revised.append(dict(target))
    elif mode=='bad_reason':target['finish_reasons']=['stop']
    elif mode=='bad_count':target['completion_tokens']=127
    else:target['timestamp_ns']=201
    router.write_text(''.join(json.dumps(x)+'\n' for x in revised));result=reconcile(inputs,root/'success/client-events.jsonl',router,root/('final-'+mode));assert result['status']=='incomplete' and result['errors'],(mode,result)
   router.write_text(''.join(json.dumps(r)+'\n' for r in server))
   router.write_text(router.read_text()+json.dumps(server[0])+'\n');bad=reconcile(inputs,root/'success/client-events.jsonl',router,root/'reconciled-duplicate');assert bad['status']=='incomplete' and bad['errors'],bad
   partial=reconcile(inputs,root/'timeout/client-events.jsonl',router,root/'reconciled-timeout');assert partial['status']=='incomplete' and partial['status_counts']['not_submitted']==28,partial
   truncated=root/'truncated.jsonl';truncated.write_text('\n'.join((root/'success/client-events.jsonl').read_text().splitlines()[:3])+'\n');interrupted=reconcile(inputs,truncated,router,root/'reconciled-interrupted');assert interrupted['status']=='incomplete' and interrupted['status_counts']['missing_client']==29,interrupted;interrupted_rows=[json.loads(x) for x in (root/'reconciled-interrupted/requests.jsonl').read_text().splitlines()];assert all(x.get('server_events') and x.get('router_id_recovered_from_client_id') for x in interrupted_rows if x['status']=='missing_client')
   recovered_client=root/'recover-client.jsonl';rc=[json.loads(x) for x in (root/'timeout/client-events.jsonl').read_text().splitlines()];timed=next(x for x in rc if x['status']=='timeout');assert not timed.get('router_id');recovered_client.write_text(''.join(json.dumps(x)+'\n' for x in rc));recovered=reconcile(inputs,recovered_client,router,root/'recovered');resultrows=[json.loads(x) for x in (root/'recovered/requests.jsonl').read_text().splitlines()];row=next(x for x in resultrows if x['request_id']==timed['request_id']);assert row['router_id_recovered_from_client_id'] and row['router_id']=='fixture-'+timed['request_id'] and row['server_events'] and row['status']=='timeout' and recovered['status']=='incomplete'
   inputfile=root/'verified-input.jsonl';checked=[]
   for i in range(32):
    ids=list(range(1023))+[2000+i];digest=hashlib.sha256((json.dumps(ids,separators=(',',':'))+'\n').encode()).hexdigest();checked.append({'request_id':str(i),'run_id':'checked','input_id':str(i),'input_ids':ids,'input_sha256':digest,'wave':i//2,'index_in_wave':i%2})
   inputfile.write_text(''.join(json.dumps(x)+'\n' for x in checked));manifest=root/'manifest.json'
   others=[]
   for length in (1024,2048):
    for concurrency in (1,2,4):
     for rep in range(5):
      if (length,concurrency,rep)==(1024,2,0):continue
      path=root/f'other-{length}-{concurrency}-{rep}.jsonl';path.write_text('fixture')
      others.append({'run_id':path.stem,'path':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'requests':32,'input_tokens':length,'output_tokens':128,'concurrency':concurrency,'repeat':rep})
   def matrix(primary):return {'runs':[primary,*others]}
   good_spec={'run_id':'checked','path':inputfile.name,'sha256':hashlib.sha256(inputfile.read_bytes()).hexdigest(),'requests':32,'input_tokens':1024,'output_tokens':128,'concurrency':2,'repeat':0}
   manifest.write_text(json.dumps(matrix(good_spec)));artifact=root/'artifact';artifact.write_text('fixture');keys=('source','baseline_source','compute_cost','communication_cost','service_configuration','scoring_rule','compatibility_evidence');freeze=root/'freeze.json';freeze.write_text(json.dumps({'status':'frozen','validation_manifest_sha256':hashlib.sha256(manifest.read_bytes()).hexdigest(),'artifacts':{k:{'path':str(artifact),'sha256':hashlib.sha256(artifact.read_bytes()).hexdigest()} for k in keys}}));preflight(freeze,manifest,'checked')
   # Re-hash deliberately invalid input to exercise semantic checks, not checksum rejection.
   for kind in ('duplicate_request','duplicate_tokens','wrong_wave_index','wrong_run','wrong_output','bad_concurrency'):
    bad=[dict(x) for x in checked];bad_spec={'run_id':'checked','path':inputfile.name,'requests':32,'input_tokens':4,'output_tokens':128,'concurrency':2}
    if kind=='duplicate_request':bad[1]['request_id']=bad[0]['request_id']
    if kind=='duplicate_tokens':bad[1]['input_ids']=bad[0]['input_ids'];bad[1]['input_sha256']=bad[0]['input_sha256']
    if kind=='wrong_wave_index':bad[1]['index_in_wave']=0
    if kind=='wrong_run':bad[1]['run_id']='other'
    if kind=='wrong_output':bad_spec['output_tokens']=64
    if kind=='bad_concurrency':bad_spec['concurrency']=3
    inputfile.write_text(''.join(json.dumps(x)+'\n' for x in bad));bad_spec['sha256']=hashlib.sha256(inputfile.read_bytes()).hexdigest();manifest.write_text(json.dumps(matrix(bad_spec)));data=json.loads(freeze.read_text());data['validation_manifest_sha256']=hashlib.sha256(manifest.read_bytes()).hexdigest();freeze.write_text(json.dumps(data))
    try:preflight(freeze,manifest,'checked');raise AssertionError(kind+' accepted')
    except ValueError:pass
   inputfile.write_text(''.join(json.dumps(x)+'\n' for x in checked));manifest.write_text(json.dumps(matrix(good_spec)));data=json.loads(freeze.read_text());data['validation_manifest_sha256']=hashlib.sha256(manifest.read_bytes()).hexdigest();freeze.write_text(json.dumps(data));artifact.write_text('tampered')
   try:preflight(freeze,manifest,'checked');raise AssertionError('tampered artifact accepted')
   except ValueError:pass
   try:preflight(root/'missing-freeze',root/'missing-manifest','x');raise AssertionError('preflight should reject missing freeze')
   except FileNotFoundError:pass
   print(json.dumps({'status':'passed','fixture_results':results,'server_reconciliation_good_and_incomplete_cases':True,'missing_freeze_and_changed_artifact_rejected':True,'scope':'synthetic local service; not real validation'},indent=2))
 finally:await runner.cleanup()
asyncio.run(main())
