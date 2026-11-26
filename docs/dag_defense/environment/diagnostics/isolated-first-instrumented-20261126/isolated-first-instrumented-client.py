import json,pathlib,sys,time,urllib.request
p=pathlib.Path(sys.argv[1]);record=json.loads(pathlib.Path(sys.argv[2]).read_text())
body={'model':'/root/autodl-tmp/models/Llama-2-7b-hf','prompt':record['input_ids'],'temperature':0,'top_p':1,'seed':0,'ignore_eos':True,'stream':False,'max_tokens':64,'min_tokens':64}
req=urllib.request.Request('http://127.0.0.1:18300/v1/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
start=time.monotonic_ns()
with urllib.request.urlopen(req,timeout=180) as response:result=json.load(response);status=response.status
end=time.monotonic_ns();p.write_text(json.dumps({'status':status,'send_ns':start,'complete_ns':end,'response':result},indent=2)+'\n')
usage=result.get('usage',{});assert status==200 and usage.get('prompt_tokens')==512 and usage.get('completion_tokens')==64
