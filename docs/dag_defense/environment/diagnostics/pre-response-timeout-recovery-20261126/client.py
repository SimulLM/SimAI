import asyncio,json,time,pathlib,sys,aiohttp
out=pathlib.Path(sys.argv[1]);events=pathlib.Path(sys.argv[2]);client_id='timeout-before-first';body={'model':'/root/autodl-tmp/models/Llama-2-7b-hf','prompt':[1,412]+[7483]*2046,'temperature':0,'top_p':1,'seed':0,'ignore_eos':True,'stream':True,'max_tokens':128,'min_tokens':128}
async def main():
 row={'client_id':client_id,'send_ns':time.monotonic_ns(),'status':'started'}
 async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
  async def request():
   async with session.post('http://127.0.0.1:18300/v1/completions',json=body,headers={'X-Experiment-Client-ID':client_id}) as resp:
    row['http_status']=resp.status;row['headers_ns']=time.monotonic_ns();row['router_id']=resp.headers.get('X-Experiment-Request-ID')
    async for line in resp.content:
     if line.startswith(b'data: '):row['first_chunk_ns']=time.monotonic_ns();break
  task=asyncio.create_task(request())
  deadline=time.monotonic()+5
  while time.monotonic()<deadline:
   if events.exists():
    for line in events.read_text().splitlines():
     event=json.loads(line)
     if event.get('event')=='server_arrival' and event.get('client_request_id')==client_id:row['router_id']=event['request_id'];row['arrival_seen_ns']=time.monotonic_ns();break
   if row.get('router_id') or task.done():break
   await asyncio.sleep(.001)
  if not row.get('router_id') or task.done():row['status']='failed_to_observe_pre_response';task.cancel()
  else:
   task.cancel()
   try:await task
   except asyncio.CancelledError:row['status']='cancelled_after_server_arrival_before_headers'
  row['client_done_ns']=time.monotonic_ns();out.write_text(json.dumps(row,indent=2)+'\n')
  if row['status']!='cancelled_after_server_arrival_before_headers':raise RuntimeError(str(row))
asyncio.run(main())
