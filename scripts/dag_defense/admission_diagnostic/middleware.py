"""Diagnostic ASGI admission fence; never certifies backend or connector idle."""
import asyncio,json,time
class AdmissionFence:
 def __init__(self,app):
  self.app=app;self.lock=asyncio.Lock();self.fenced=False;self.active=0;self.accepted=0;self.finished=0
 async def reply(self,send,status,payload):
  raw=json.dumps(payload,separators=(',',':')).encode();await send({'type':'http.response.start','status':status,'headers':[(b'content-type',b'application/json')]});await send({'type':'http.response.body','body':raw})
 async def __call__(self,scope,receive,send):
  if scope['type']!='http':return await self.app(scope,receive,send)
  path=scope.get('path');method=scope.get('method')
  if path=='/_diagnostic/admission' and method=='POST':
   raw=b''
   while True:
    msg=await receive()
    if msg['type']!='http.request':return
    raw+=msg.get('body',b'')
    if len(raw)>1024:return await self.reply(send,413,{'error':'too_large'})
    if not msg.get('more_body'):break
   try:action=json.loads(raw).get('action')
   except Exception:return await self.reply(send,400,{'error':'bad_json'})
   if action not in ('fence','open','status'):return await self.reply(send,400,{'error':'bad_action'})
   async with self.lock:
    if action=='fence':self.fenced=True
    if action=='open':
     if self.active:return await self.reply(send,409,{'error':'active_requests'})
     self.fenced=False
    state={'fenced':self.fenced,'active':self.active,'accepted':self.accepted,'finished':self.finished,'timestamp_ns':time.monotonic_ns()}
   return await self.reply(send,200,state)
  if path!='/v1/completions' or method!='POST':return await self.app(scope,receive,send)
  async with self.lock:
   if self.fenced:rejected=True
   else:self.active+=1;self.accepted+=1;rejected=False
  if rejected:return await self.reply(send,503,{'error':'admission_fenced'})
  try:return await self.app(scope,receive,send)
  finally:
   async with self.lock:self.active-=1;self.finished+=1
