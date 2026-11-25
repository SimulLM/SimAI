import os
import json,glob
from pathlib import Path
r=Path(os.environ['PD_RUN_DIR'])
client=json.loads((r/'client-events.json').read_text()); mapping=client[-1]
assert mapping['event']=='request_mapping'
def events(role, rid):
 for path in glob.glob(str(r/f'events-{role}-*.jsonl')):
  data=[json.loads(x) for x in Path(path).read_text().splitlines()]
  if any(any(g['request_id']==rid+'-0' for g in e.get('groups',[])) for e in data): return data
 raise AssertionError('missing worker events for '+rid)
p=events('prefill',mapping['prefill_id']);d=events('decode',mapping['decode_id'])
def one(data,name):
 rows=[e for e in data if e['event']==name]
 assert len(rows)==1,(name,len(rows));return rows[0]
a=one(p,'prefill_gpu_complete_before_kv_insert');b=one(p,'kv_insert_cpu'); c=one(d,'kv_ready_gpu_complete')
assert b['tokens']==6 and (b['key_bytes'],b['value_bytes'],b['hidden_bytes'])==(1572864,1572864,49152)
assert c['bypass_model_exec'] is True
sends=[e for e in p if e['event']=='transport_send_gpu_complete']; recvs=[e for e in d if e['event']=='transport_recv_gpu_complete']
assert [x['bytes'] for x in sends]==[48,24,1572864,1572864,49152]
assert [x['bytes'] for x in recvs]==[48,24,1572864,1572864,49152]
decode=[e for e in d if e['event']=='model_step_cpu_start' and any(not g['is_prompt'] and g['request_id']==mapping['decode_id']+'-0' for g in e['groups'])]
assert a['timestamp_ns'] < b['timestamp_ns'] < sends[0]['timestamp_ns'] < c['timestamp_ns'] < decode[0]['timestamp_ns'] < client[3]['timestamp_ns']
assert max(e['timestamp_ns'] for e in recvs)<c['timestamp_ns']
print('PASS: mapped IDs, 6 tokens, KV and hidden byte counts, ordered GPU-synchronized diagnostic milestones, bypass, and response')
