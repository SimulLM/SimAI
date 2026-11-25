import asyncio,json,time,uuid,os
from quart import Quart,request,Response
import aiohttp
app=Quart(__name__)
path='/root/autodl-tmp/dag-handoff/runs/observed-proxy-events.jsonl'
def event(rid,name,**kw):
 row={'request_id':rid,'event':name,'timestamp_ns':time.monotonic_ns(),'clock_id':'CLOCK_MONOTONIC','pid':os.getpid(),**kw}
 with open(path,'a') as f: f.write(json.dumps(row)+'\n')
@app.post('/v1/completions')
async def complete():
 rid=uuid.uuid4().hex; body=await request.get_json(); event(rid,'server_arrival')
 if body.get('stream'): return {'error':'stream not supported in diagnostic'},400
 p=dict(body); p['max_tokens']=1; p['min_tokens']=0
 try:
  async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as s:
   event(rid,'prefill_request_send')
   async with s.post('http://127.0.0.1:8100/v1/completions',json=p) as r:
    content=await r.read(); event(rid,'prefill_response',status=r.status,backend_request_id=json.loads(content).get('id') if r.status==200 else None)
    if r.status!=200: return Response(content,status=r.status,content_type='application/json')
   event(rid,'decode_request_send')
   async with s.post('http://127.0.0.1:8200/v1/completions',json=body) as r:
    content=await r.read(); event(rid,'server_complete',status=r.status,backend_request_id=json.loads(content).get('id') if r.status==200 else None)
    return Response(content,status=r.status,content_type='application/json',headers={'X-Experiment-Request-ID':rid})
 except Exception as e:
  event(rid,'error',error=type(e).__name__); return {'error':type(e).__name__},502
if __name__=='__main__': app.run(host='127.0.0.1',port=8400)
