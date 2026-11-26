"""Replay fixed calibration input twice through the streaming diagnostic router."""
import hashlib,json,pathlib,sys,time,urllib.request
ref=json.loads(pathlib.Path(sys.argv[1]).read_text());out=pathlib.Path(sys.argv[2]);ids=ref['input_ids']
assert len(ids)==512 and hashlib.sha256(json.dumps(ids,separators=(',',':')).encode()).hexdigest()==ref['input_sha256']
body={'model':'/root/autodl-tmp/models/Llama-2-7b-hf','prompt':ids,'temperature':0,'top_p':1,'seed':0,'ignore_eos':True,'stream':True,'max_tokens':64,'min_tokens':64}
rows=[]
for index in range(25):
 stage=('warmup-' if index<5 else 'measured-')+str(index)
 req=urllib.request.Request('http://127.0.0.1:18300/v1/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json','X-Experiment-Client-ID':'single-stream-'+stage});row={'stage':stage,'client_send_ns':time.monotonic_ns(),'done':False,'chunks':[]}
 with urllib.request.urlopen(req,timeout=180) as response:
  row['http_status']=response.status;row['router_id']=response.headers.get('X-Experiment-Request-ID');row['client_headers_ns']=time.monotonic_ns()
  for raw in response:
   now=time.monotonic_ns()
   if not raw.startswith(b'data: '):continue
   value=raw[6:].strip()
   if value==b'[DONE]':row['done']=True;row['client_done_ns']=now;continue
   item=json.loads(value);row['backend_id']=item.get('id',row.get('backend_id'));usage=item.get('usage')
   if usage is not None:row['usage']=usage
   row['chunks'].append({'ns':now,'usage':usage,'choices':item.get('choices')})
 row['client_complete_ns']=time.monotonic_ns();rows.append(row)
 with out.open('w') as f:json.dump(rows,f,indent=2)
 assert row['http_status']==200 and row['done'] and row['router_id'] and row['backend_id'] and row['usage']['prompt_tokens']==512 and row['usage']['completion_tokens']==64
