import os
import json,time,requests
from pathlib import Path
run=Path(os.environ['PD_RUN_DIR'])
model='/root/autodl-tmp/models/Llama-2-7b-hf'
base=dict(model=model,prompt='The capital of France is',temperature=0,top_p=1,seed=0,ignore_eos=True,stream=False)
rows=[]
def event(name,**kw): rows.append(dict(event=name,timestamp_ns=time.monotonic_ns(),clock_id='CLOCK_MONOTONIC',**kw))
def call(port,**params):
 event('client_send',port=port)
 r=requests.post(f'http://127.0.0.1:{port}/v1/completions',json={**base,**params},timeout=120)
 event('client_complete',port=port,status=r.status_code)
 r.raise_for_status(); response=r.json(); (run/f'response-{port}.json').write_text(json.dumps(response,indent=2)+'\n'); return response
try:
 p=call(18100,max_tokens=1,min_tokens=0)
 d=call(18200,max_tokens=8,min_tokens=8)
 event('request_mapping',prefill_id=p['id'],decode_id=d['id'])
 assert d['usage']['prompt_tokens']==6 and d['usage']['completion_tokens']==8
finally:
 (run/'client-events.json').write_text(json.dumps(rows,indent=2)+'\n')
