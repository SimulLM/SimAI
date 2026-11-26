import os, json, time, uuid
import aiohttp
from quart import Quart, request, Response
app=Quart(__name__)
path=os.path.join(os.environ['COMPUTE_DIAG_DIR'],'router-events.jsonl')
def log(r):
 with open(path,'a') as f: f.write(json.dumps(r,separators=(',',':'))+'\n')
@app.route('/v1/completions',methods=['POST'])
async def handle():
 row={'router_id':uuid.uuid4().hex,'arrival_ns':time.monotonic_ns(),'clock_id':'CLOCK_MONOTONIC'}
 try:
  data=await request.get_json()
  if data.get('stream',False): raise ValueError('diagnostic supports non-stream requests only')
  pre=dict(data);pre.update(max_tokens=1,min_tokens=0)
  async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=300)) as s:
   row['prefill_submit_ns']=time.monotonic_ns()
   async with s.post('http://127.0.0.1:8100/v1/completions',json=pre) as r:
    p=await r.read();row.update(prefill_status=r.status,prefill_done_ns=time.monotonic_ns()); pref=json.loads(p);row['prefill_id']=pref.get('id')
    if r.status!=200: raise RuntimeError('prefill status '+str(r.status))
   row['decode_submit_ns']=time.monotonic_ns()
   async with s.post('http://127.0.0.1:8200/v1/completions',json=data) as r:
    body=await r.read(); row.update(decode_status=r.status,decode_done_ns=time.monotonic_ns()); decoded=json.loads(body);row['decode_id']=decoded.get('id'); status=r.status
  row['router_complete_ns']=time.monotonic_ns();log(row)
  return Response(body,status=status,content_type='application/json')
 except Exception as e:
  row.update(error=repr(e),router_complete_ns=time.monotonic_ns());log(row)
  return Response('diagnostic error',status=500)
if __name__=='__main__': app.run(port=18300)
