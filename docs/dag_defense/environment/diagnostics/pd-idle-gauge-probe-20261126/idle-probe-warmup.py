import json,pathlib,sys,urllib.request
body={'model':'/root/autodl-tmp/models/Llama-2-7b-hf','prompt':[1]+[7483]*511,'temperature':0,'top_p':1,'seed':0,'ignore_eos':True,'stream':True,'max_tokens':64,'min_tokens':64}
req=urllib.request.Request('http://127.0.0.1:18300/v1/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'});done=False;usage=None;backend=None
with urllib.request.urlopen(req,timeout=180) as resp:
 rid=resp.headers.get('X-Experiment-Request-ID');status=resp.status
 for raw in resp:
  if not raw.startswith(b'data: '):continue
  data=raw[6:].strip()
  if data==b'[DONE]':done=True;continue
  obj=json.loads(data);backend=obj.get('id',backend);usage=obj.get('usage') or usage
result={'nature':'diagnostic warmup only','status':status,'router_id':rid,'backend_id':backend,'done':done,'usage':usage};pathlib.Path(sys.argv[1]).write_text(json.dumps(result,indent=2)+'\n')
if not(done and status==200 and rid and backend and usage and usage.get('prompt_tokens')==512 and usage.get('completion_tokens')==64):raise SystemExit(1)
