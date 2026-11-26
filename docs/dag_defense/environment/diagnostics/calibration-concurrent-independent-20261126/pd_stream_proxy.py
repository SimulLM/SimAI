"""Local 1P1D streaming diagnostic router; monotonic API boundary events."""
import json,os,time,uuid
from contextlib import asynccontextmanager
import aiohttp
from fastapi import FastAPI,Request
from fastapi.responses import JSONResponse,Response,StreamingResponse
run=os.environ['PD_ROUTE_DIR']; timeout=aiohttp.ClientTimeout(total=180)
def event(rid,name,**fields):
 row=dict(request_id=rid,event=name,timestamp_ns=time.monotonic_ns(),clock_id='CLOCK_MONOTONIC',pid=os.getpid(),**fields)
 data=(json.dumps(row,separators=(',',':'))+'\n').encode()
 fd=os.open(os.path.join(run,'router-events.jsonl'),os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
 try:os.write(fd,data)
 finally:os.close(fd)
@asynccontextmanager
async def lifespan(app):
 app.state.session=aiohttp.ClientSession(timeout=timeout)
 yield
 await app.state.session.close()
app=FastAPI(lifespan=lifespan)
@app.post('/v1/completions')
async def complete(request:Request):
 rid=uuid.uuid4().hex; event(rid,'server_arrival')
 try:
  body=await request.json()
  if body.get('stream') is not True:
   event(rid,'server_error',stage='validation',error='stream_required');return JSONResponse({'error':'stream_required'},status_code=400)
  pre=dict(body);pre.update(max_tokens=1,min_tokens=0,stream=False);pre.pop('stream_options',None)
  event(rid,'prefill_send')
  async with app.state.session.post('http://127.0.0.1:18100/v1/completions',json=pre) as resp:
   raw=await resp.read(); event(rid,'prefill_response',status=resp.status)
   if resp.status!=200:
    event(rid,'server_error',stage='prefill',status=resp.status);return Response(raw,status_code=resp.status,media_type='application/json',headers={'X-Experiment-Request-ID':rid})
   p=json.loads(raw);event(rid,'prefill_mapping',backend_request_id=p['id'])
  decode=dict(body);decode['stream_options']={'include_usage':True,'continuous_usage_stats':True}
  event(rid,'decode_send')
  resp=await app.state.session.post('http://127.0.0.1:18200/v1/completions',json=decode)
  if resp.status!=200:
   raw=await resp.read();status=resp.status;resp.release();event(rid,'server_error',stage='decode',status=status);return Response(raw,status_code=status,media_type='application/json',headers={'X-Experiment-Request-ID':rid})
  async def stream():
   first=False;done=False;seen_id=False;usage=None
   try:
    async for line in resp.content:
     if line.startswith(b'data: '):
      val=line[6:].strip()
      if val==b'[DONE]':done=True
      else:
       try:
        data=json.loads(val)
        if data.get('id') and not seen_id:event(rid,'decode_mapping',backend_request_id=data['id']);seen_id=True
        choices=data.get('choices') or []
        if data.get('usage') and data['usage'].get('completion_tokens',0)>0 and not first:event(rid,'server_first_token');first=True
        if data.get('usage') is not None:usage=data['usage']
       except (ValueError,TypeError):pass
     yield line
    if done and seen_id and usage is not None:event(rid,'server_complete',usage=usage)
    else:event(rid,'server_error',stage='decode_stream',error='incomplete_stream',done=done,seen_id=seen_id,usage_present=usage is not None)
   except BaseException as exc:
    event(rid,'server_error',stage='decode_stream',error=type(exc).__name__);raise
   finally:resp.release()
  return StreamingResponse(stream(),media_type='text/event-stream',headers={'X-Experiment-Request-ID':rid})
 except Exception as exc:
  event(rid,'server_error',stage='routing',error=type(exc).__name__);return JSONResponse({'error':type(exc).__name__},status_code=502,headers={'X-Experiment-Request-ID':rid})
