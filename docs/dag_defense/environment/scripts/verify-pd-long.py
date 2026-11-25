import glob,json,os
from pathlib import Path
r=Path(os.environ['PD_RUN_DIR']); rows=json.loads((r/'concurrent-partial.json').read_text()); assert len(rows)==8
for port in (18100,18200):
 rs=[x for x in rows if x['port']==port]; assert sorted(x['index'] for x in rs)==list(range(4))
 for x in rs:
  assert x['status']==200 and x['response']['usage']['prompt_tokens']==2048
  if port==18200: assert x['response']['usage']['completion_tokens']==2
ids={x['response']['id']+'-0' for x in rows}; events=[]
for path in glob.glob(str(r/'events-*.jsonl')):
 events.extend(json.loads(x) for x in Path(path).read_text().splitlines())
insert=[e for e in events if e['event']=='kv_insert_cpu' and any(g['request_id'] in ids for g in e['groups'])]
assert len(insert)==4 and all(e['tokens']==2048 and e['key_bytes']==536870912 and e['value_bytes']==536870912 and e['hidden_bytes']==16777216 for e in insert)
ready=[e for e in events if e['event']=='kv_ready_gpu_complete' and any(g['request_id'] in ids for g in e['groups'])]
ready_ids=[g['request_id'] for e in ready if e['bypass_model_exec'] for g in e['groups'] if g['request_id'] in ids]
expected=[x['response']['id']+'-0' for x in rows if x['port']==18200]
assert sorted(ready_ids)==sorted(expected)
p_batches=[e for e in events if e['event']=='model_step_cpu_start' and e['role']=='prefill' and any(g['request_id'] in ids for g in e['groups'])]
d_batches=[e for e in events if e['event']=='model_step_cpu_start' and e['role']=='decode' and any(g['request_id'] in ids and not g['is_prompt'] for g in e['groups'])]
print('PASS: 4 unique 2048-token requests; all 8 responses HTTP 200; all four consumer IDs reported KVReady/bypass; producer insertion sizes verified')
print('prefill batch sizes:',[len(e['groups']) for e in p_batches],'; decode step batch sizes:',[len(e['groups']) for e in d_batches])
