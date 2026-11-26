"""Check slow or failing durable writes do not silently distort peer collection."""
import asyncio,json,pathlib,tempfile,time
from aiohttp import web
import collect_validation_run as collector

def test_slow_and_failed_writer():
 async def main():
  async def handle(req):
   body=await req.json();i=body['prompt'][1]
   if i==1:await asyncio.sleep(.08)
   usage={'prompt_tokens':4,'completion_tokens':128};payload='data: '+json.dumps({'id':str(i),'usage':usage})+'\n\ndata: [DONE]\n\n'
   return web.Response(text=payload,content_type='text/event-stream',headers={'X-Experiment-Request-ID':str(i)})
  app=web.Application();app.router.add_post('/v1/completions',handle);runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start();port=site._server.sockets[0].getsockname()[1]
  original=collector.append
  try:
   with tempfile.TemporaryDirectory() as tmp:
    root=pathlib.Path(tmp);rows=[{'run_id':'x','request_id':str(i),'input_id':str(i),'input_sha256':str(i),'wave':0,'input_ids':[1,i]} for i in range(2)];spec={'run_id':'x','input_tokens':4,'concurrency':2,'requests':2}
    def slow(path,row):
     if path.name=='client-events.jsonl':time.sleep(.5)
     original(path,row)
    collector.append=slow
    await collector.run_case(spec,rows,root/'slow',f'http://127.0.0.1:{port}/v1/completions','test',5)
    result=[json.loads(x) for x in (root/'slow/client-events.jsonl').read_text().splitlines()];assert len(result)==2 and all(x['status']=='success' for x in result)
    result.sort(key=lambda x:x['request_id']);assert 0 < (result[1]['client_complete_ns']-result[0]['client_complete_ns'])/1e9 < .35
    def fail(path,row):
     if path.name=='client-events.jsonl':raise OSError('injected storage failure')
     original(path,row)
    collector.append=fail
    try:await collector.run_case(spec,rows,root/'fail',f'http://127.0.0.1:{port}/v1/completions','test',5)
    except OSError as e:assert 'injected storage failure' in str(e)
    else:raise AssertionError('storage failure did not propagate')
    assert not (root/'fail/client-complete.json').exists()
  finally:collector.append=original;await runner.cleanup()
 asyncio.run(main())
