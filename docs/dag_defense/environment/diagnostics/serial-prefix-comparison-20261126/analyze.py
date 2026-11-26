import collections,csv,glob,json,pathlib,statistics
source=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/light-serial-512-20261126');out=pathlib.Path(__file__).parent
clients=json.loads((source/'client.json').read_text())[5:];assert len(clients)==20
r=collections.defaultdict(dict)
for line in (source/'service/router-events.jsonl').open():
 x=json.loads(line);r[x['request_id']][x['event']]=x
worker=collections.defaultdict(list)
for f in (source/'service/events').glob('*.jsonl'):
 for line in f.open():
  x=json.loads(line)
  for g in x.get('groups',[]):worker[g['request_id']].append(x)
rows=[]
for c in clients:
 ev=r[c['router_id']];origin=ev['server_arrival']['timestamp_ns'];pr=ev['prefill_mapping']['backend_request_id']+'-0';dr=c['backend_id']+'-0'
 def find(rid,name):
  a=[x for x in worker[rid] if x['event']==name];assert len(a)==1,(name,len(a));return a[0]['timestamp_ns']
 def one(name):return ev[name]['timestamp_ns']
 p_start=min(x['timestamp_ns'] for x in worker[pr] if x['event']=='model_step_host_start');p_end=max(x['timestamp_ns'] for x in worker[pr] if x['event']=='model_step_host_return')
 d_start=min(x['timestamp_ns'] for x in worker[dr] if x['event']=='model_step_host_start');d_end=min(x['timestamp_ns'] for x in worker[dr] if x['event']=='model_step_host_return')
 t=[origin,one('prefill_send'),p_start,find(pr,'send_kv_caches_and_hidden_states_host_start'),find(pr,'send_kv_caches_and_hidden_states_host_return'),p_end,one('prefill_response'),one('decode_send'),d_start,find(dr,'recv_kv_caches_and_hidden_states_host_start'),find(dr,'recv_kv_caches_and_hidden_states_host_return'),d_end,one('server_first_token')]
 assert all(x<=y for x,y in zip(t,t[1:]));row={'router_id':c['router_id']}
 for n,v in zip(['arrival','prefill_send','prefill_worker_start','producer_send_start','producer_send_return','prefill_worker_return','prefill_response','decode_send','decode_worker_start','receive_start','receive_return','first_step_return','router_first'],t):row[n+'_ms']=(v-origin)/1e6
 rows.append(row)
with (out/'requests.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
summary={k:{'median_ms':statistics.median(row[k] for row in rows),'min_ms':min(row[k] for row in rows),'max_ms':max(row[k] for row in rows)} for k in rows[0] if k.endswith('_ms')}
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
