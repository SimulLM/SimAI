import json,os,time,requests
from pathlib import Path
r=Path(os.environ['PD_RUN_DIR']); model='/root/autodl-tmp/models/Llama-2-7b-hf'
prompt=([1]+[450,7483,310,3444,338]*410)[:2048]
assert len(prompt)==2048
body=dict(model=model,prompt=prompt,temperature=0,top_p=1,seed=0,ignore_eos=True,stream=False)
(r/'input.json').write_text(json.dumps(dict(token_ids=prompt,token_count=len(prompt)))+'\n')
events=[]
def invoke(port,**kw):
 events.append(dict(event='send',port=port,timestamp_ns=time.monotonic_ns()))
 response=requests.post(f'http://127.0.0.1:{port}/v1/completions',json={**body,**kw},timeout=180)
 events.append(dict(event='complete',port=port,timestamp_ns=time.monotonic_ns(),status=response.status_code))
 response.raise_for_status(); out=response.json(); (r/f'response-{port}.json').write_text(json.dumps(out,indent=2)+'\n'); return out
try:
 p=invoke(18100,max_tokens=1,min_tokens=0)
 d=invoke(18200,max_tokens=2,min_tokens=2)
 events.append(dict(event='mapping',prefill_id=p['id'],decode_id=d['id'],timestamp_ns=time.monotonic_ns()))
 assert p['usage']['prompt_tokens']==2048 and d['usage']['prompt_tokens']==2048 and d['usage']['completion_tokens']==2
finally:
 (r/'client-events.json').write_text(json.dumps(events,indent=2)+'\n')
