"""Audit a single real PD smoke; host returns are not GPU completion."""
import collections,json,pathlib,sys
root=pathlib.Path(sys.argv[1]);client=json.loads((root/'request.json').read_text())
router=[json.loads(x) for x in (root/'service/router-events.jsonl').read_text().splitlines()]
assert client['status']==200 and client['done'] and client['usage']['prompt_tokens']==512 and client['usage']['completion_tokens']==64
rid=client['router_id'];route=[x for x in router if x['request_id']==rid];by={}
for e in route:by.setdefault(e['event'],[]).append(e)
for k in ('server_arrival','prefill_mapping','decode_mapping','server_complete'):assert len(by.get(k,[]))==1
prefill=by['prefill_mapping'][0]['backend_request_id']+'-0';decode=by['decode_mapping'][0]['backend_request_id']+'-0'
assert decode==client['backend_id']+'-0'
logs=[]
for p in (root/'service/events').glob('*.jsonl'):
 logs.extend(json.loads(x) for x in p.read_text().splitlines())
def find(role,name,request):
 rows=[x for x in logs if x.get('role')==role and x['event']==name and any(g['request_id']==request for g in x.get('groups',[]))]
 assert len(rows)==1,(role,name,len(rows));return rows[0]
p1=find('producer','send_kv_caches_and_hidden_states_host_start',prefill);p2=find('producer','send_kv_caches_and_hidden_states_host_return',prefill)
d1=find('consumer','recv_kv_caches_and_hidden_states_host_start',decode);d2=find('consumer','recv_kv_caches_and_hidden_states_host_return',decode)
assert d2['kv_bypass'] is True and p1['step_id']==p2['step_id'] and d1['step_id']==d2['step_id']
assert by['server_arrival'][0]['timestamp_ns']<=p1['timestamp_ns']<=p2['timestamp_ns']<=d1['timestamp_ns']<=d2['timestamp_ns']<=by['server_complete'][0]['timestamp_ns']
for event in (p1,p2,d1,d2):assert event['clock_id']=='CLOCK_MONOTONIC'
result={'status':'host_event_smoke_pass','router_id':rid,'prefill_id':prefill,'decode_id':decode,'kv_bypass':True,'events':[p1,p2,d1,d2],'limitations':['Host return is not GPU completion or exact KVReady','Single success only; concurrency, timeout cleanup and logging overhead not validated','Diagnostic smoke, not formal validation']}
(root/'audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
