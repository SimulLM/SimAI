"""Exercise actual router against local fake backends; no model or GPU involved."""
import asyncio,importlib.util,json,os,pathlib,tempfile
from aiohttp import web
import httpx
async def main():
 with tempfile.TemporaryDirectory() as temp:
  os.environ['PD_ROUTE_DIR']=temp
  spec=importlib.util.spec_from_file_location('test_pd_proxy',pathlib.Path(__file__).resolve().parents[2]/'docs/dag_defense/environment/scripts/pd_stream_proxy.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  app=web.Application()
  async def prefill(req):
   body=await req.json()
   if body.get('model')=='slow':await asyncio.sleep(.3)
   return web.json_response({'id':'fake-prefill'})
  app.router.add_post('/v1/completions',prefill);runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',18100);await site.start()
  app2=web.Application()
  async def decode(req):
   body=await req.json();count=128 if body.get('model')=='final-only' else 1
   payload='data: '+json.dumps({'id':'fake-decode','usage':{'completion_tokens':count},'choices':[{'finish_reason':'length'}]})+'\n\ndata: [DONE]\n\n';return web.Response(text=payload,content_type='text/event-stream')
  app2.router.add_post('/v1/completions',decode);runner2=web.AppRunner(app2);await runner2.setup();await web.TCPSite(runner2,'127.0.0.1',18200).start()
  try:
   async with module.app.router.lifespan_context(module.app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app),base_url='http://test') as client:
     response=await client.post('/v1/completions',headers={'X-Experiment-Client-ID':'run-req0'},json={'model':'fast','stream':True});assert response.status_code==200
     rid=response.headers['X-Experiment-Request-ID']
     try:await asyncio.wait_for(client.post('/v1/completions',headers={'X-Experiment-Client-ID':'run-req1'},json={'model':'slow','stream':True}),timeout=.05);raise AssertionError('timeout was expected')
     except asyncio.TimeoutError:pass
     final_only=await client.post('/v1/completions',headers={'X-Experiment-Client-ID':'run-req2'},json={'model':'final-only','stream':True});assert final_only.status_code==200;final_rid=final_only.headers['X-Experiment-Request-ID']
     bad=await client.post('/v1/completions',headers={'X-Experiment-Client-ID':'bad id'},json={'stream':True});assert bad.status_code==400
   events=[json.loads(x) for x in (pathlib.Path(temp)/'router-events.jsonl').read_text().splitlines()];arrivals=[x for x in events if x['event']=='server_arrival'];assert len(arrivals)==3 and {x['client_request_id'] for x in arrivals}=={'run-req0','run-req1','run-req2'} and next(x for x in arrivals if x['client_request_id']=='run-req0')['request_id']==rid
   ordered=[e for e in events if e['request_id']==rid]; names=[e['event'] for e in ordered]; assert names.index('server_final_choice_observed') < names.index('server_complete'); final=next(e for e in ordered if e['event']=='server_final_choice_observed'); assert final['finish_reasons']==['length'] and final['completion_tokens']==1
   wrong=[e for e in events if e['request_id']==final_rid];assert not any(e['event'] in ('server_first_token','server_complete') for e in wrong);assert any(e['event']=='server_error' and e.get('first_observed_completion_tokens')==128 for e in wrong)
   print('PASS: actual router records stable client ID before backend response; timeout and invalid ID covered; fake backends only')
  finally:await runner.cleanup();await runner2.cleanup()
asyncio.run(main())
