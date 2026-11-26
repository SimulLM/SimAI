"""Independent serial PD cache-install diagnostic input waves."""
import json,pathlib,sys,time,urllib.request
out=pathlib.Path(sys.argv[1]);model='/root/autodl-tmp/models/Llama-2-7b-hf'
for length in (512,1024,2048):
 for wave in range(40):
  ids=([1,450+wave]+[7483,310,3444,338]*((length+3)//4))[:length]
  body={'model':model,'prompt':ids,'temperature':0,'top_p':1,'seed':0,'ignore_eos':True,'stream':True,'max_tokens':8,'min_tokens':8}
  req=urllib.request.Request('http://127.0.0.1:18300/v1/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json','X-Experiment-Client-ID':f'install-{length}-{wave}'})
  row={'length':length,'wave':wave,'warmup':wave<10,'send_ns':time.monotonic_ns(),'done':False}
  try:
   with urllib.request.urlopen(req,timeout=120) as res:
    row['status']=res.status;row['router_id']=res.headers.get('X-Experiment-Request-ID')
    for raw in res:
     if not raw.startswith(b'data: '):continue
     val=raw[6:].strip()
     if val==b'[DONE]':row['done']=True;continue
     d=json.loads(val);row['backend_id']=d.get('id',row.get('backend_id'));row['usage']=d.get('usage') or row.get('usage')
  finally:
   row['complete_ns']=time.monotonic_ns()
   with out.open('a') as f:f.write(json.dumps(row,separators=(',',':'))+'\n');f.flush()
  assert row['status']==200 and row['done'] and row['usage']['prompt_tokens']==length and row['usage']['completion_tokens']==8
