import asyncio,json,httpx
from middleware import AdmissionFence
async def main():
 started=asyncio.Event();release=asyncio.Event()
 async def downstream(scope,receive,send):
  if scope['path']=='/v1/completions':
   started.set();await release.wait()
   await send({'type':'http.response.start','status':200,'headers':[]});await send({'type':'http.response.body','body':b'done'})
  else:
   await send({'type':'http.response.start','status':404,'headers':[]});await send({'type':'http.response.body','body':b''})
 app=AdmissionFence(downstream)
 async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://local') as client:
  task=asyncio.create_task(client.post('/v1/completions'));await asyncio.wait_for(started.wait(),2)
  f=await client.post('/_diagnostic/admission',json={'action':'fence'});assert f.status_code==200 and f.json()['active']==1 and f.json()['accepted']==1
  assert (await client.post('/v1/completions')).status_code==503
  assert (await client.post('/_diagnostic/admission',json={'action':'open'})).status_code==409
  release.set();assert (await task).status_code==200
  state=(await client.post('/_diagnostic/admission',json={'action':'status'})).json();assert state['active']==0 and state['accepted']==state['finished']==1 and state['fenced']
  assert (await client.post('/_diagnostic/admission',json={'action':'open'})).json()['fenced'] is False
  assert (await client.post('/v1/completions')).status_code==200
  assert (await client.post('/_diagnostic/admission',json={'action':'unknown'})).status_code==400
  # Cancellation must decrement the ASGI in-flight counter but is not proof of backend cleanup.
  release.clear();started.clear();task=asyncio.create_task(client.post('/v1/completions'));await asyncio.wait_for(started.wait(),2);task.cancel()
  try:await task
  except asyncio.CancelledError:pass
  state=(await client.post('/_diagnostic/admission',json={'action':'status'})).json();assert state['active']==0 and state['accepted']==state['finished']==3
 print('PASS fenced inflight, rejection, drain, reopen, cancellation')
asyncio.run(main())
