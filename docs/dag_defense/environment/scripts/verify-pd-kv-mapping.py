import glob,hashlib,json,os,struct
from pathlib import Path
r=Path(os.environ['PD_RUN_DIR']);inputs=json.loads((r/'concurrent-inputs.json').read_text())['token_ids'];rows=json.loads((r/'concurrent-partial.json').read_text());assert len(inputs)==4 and len(rows)==8 and (r/'concurrent-exit-code').read_text().strip()=='0'
hashes=[hashlib.sha256(struct.pack('<'+'q'*len(ids),*ids)).hexdigest() for ids in inputs];assert len(set(hashes))==4 and all(len(ids)==2048 for ids in inputs)
events=[]
for path in glob.glob(str(r/'events-*.jsonl')):events.extend(json.loads(x) for x in Path(path).read_text().splitlines())
report=[]
for i,h in enumerate(hashes):
 p=[x for x in rows if x['port']==18100 and x['index']==i];d=[x for x in rows if x['port']==18200 and x['index']==i];assert len(p)==len(d)==1 and p[0]['status']==d[0]['status']==200
 pre=p[0]['response']['id']+'-0';dec=d[0]['response']['id']+'-0'
 inserts=[e for e in events if e['event']=='kv_insert_cpu' and e.get('token_sha256')==h];matches=[e for e in events if e['event']=='kv_select_match' and e.get('query_sha256')==h];assert len(inserts)==len(matches)==1
 ins,mat=inserts[0],matches[0];assert any(g['request_id']==pre for g in ins['groups']) and any(g['request_id']==dec for g in mat['groups'])
 assert mat['returned_sha256']==h and ins['tokens']==mat['tokens']==2048
 assert (ins['key_bytes'],ins['value_bytes'],ins['hidden_bytes'])==(536870912,536870912,16777216)
 ready=[e for e in events if e['event']=='kv_ready_gpu_complete' and e['bypass_model_exec'] and any(g['request_id']==dec for g in e['groups'])];assert len(ready)==1 and ins['timestamp_ns']<mat['timestamp_ns']<ready[0]['timestamp_ns']
 report.append(dict(index=i,input_sha256=h,prefill_backend_id=pre,decode_backend_id=dec,insert_ns=ins['timestamp_ns'],match_ns=mat['timestamp_ns'],kv_ready_ns=ready[0]['timestamp_ns']))
result=dict(status='passed',requests=report,notes='SHA256 covers token IDs, not KV tensor bytes; association relies on SimpleBuffer matching and bundled item semantics. Synchronizing diagnostic only.')
(r/'mapping-verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
