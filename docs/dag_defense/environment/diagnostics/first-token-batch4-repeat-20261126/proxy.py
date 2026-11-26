import os,json,time,uuid,asyncio
import aiohttp
from quart import Quart,request,Response
app=Quart(__name__);path=os.path.join(os.environ['COMPUTE_DIAG_DIR'],'router-events.jsonl');lock=asyncio.Lock();batch=[];current=asyncio.Event()
def log(row):
 with open(path,'a') as f:f.write(json.dumps(row,separators=(',',':'))+'\n');f.flush()
@app.route('/v1/completions',methods=['POST'])
async def handle():
 global batch,current
 row={'router_id':uuid.uuid4().hex,'arrival_ns':time.monotonic_ns(),'clock_id':'CLOCK_MONOTONIC'}
 try:
  data=await request.get_json()
  if data.get('stream',False):raise ValueError('non-stream only')
  pre=dict(data);pre.update(max_tokens=1,min_tokens=0)
  async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as s:
   row['prefill_submit_ns']=time.monotonic_ns()
   async with s.post('http://127.0.0.1:8100/v1/completions',json=pre) as r:
    body=await r.read(); row.update(prefill_status=r.status,prefill_done_ns=time.monotonic_ns());row['prefill_id']=json.loads(body).get('id')
    if r.status!=200:raise RuntimeError('prefill failed')
   async with lock:
    event=current;batch.append(row['router_id']);row['group_position']=len(batch)
    if len(batch)==4:batch=[];current=asyncio.Event();event.set()
   await asyncio.wait_for(event.wait(),timeout=30)
   row['decode_submit_ns']=time.monotonic_ns()
   async with s.post('http://127.0.0.1:8200/v1/completions',json=data) as r:
    body=await r.read();row.update(decode_status=r.status,decode_done_ns=time.monotonic_ns());row['decode_id']=json.loads(body).get('id');status=r.status
  row['router_complete_ns']=time.monotonic_ns();log(row);return Response(body,status=status,content_type='application/json')
 except Exception as e:
  row.update(error=repr(e),router_complete_ns=time.monotonic_ns());log(row);return Response('diagnostic error',status=500)
if __name__=='__main__':app.run(port=18300)
