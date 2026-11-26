import json, pathlib, collections, statistics
p=pathlib.Path(__file__).parent
load=lambda f:[json.loads(x) for x in f.read_text().splitlines()]
requests=load(p/'coverage/requests.jsonl'); routers=load(p/'router-events.jsonl')
router_by_decode={x.get('decode_id'):x for x in routers if x.get('decode_id')}
byid=collections.defaultdict(list)
for f in p.glob('compute-events-*.jsonl'):
 for e in load(f):
  if e.get('event')=='model_step':
   for rid in e.get('request_ids_to_seq_ids',{}): byid[rid].append(e)
counts=collections.Counter(); defects=[]; pairs=[]; unique=collections.defaultdict(dict)
for r in requests:
 route=router_by_decode.get(r.get('backend_request_id')); reasons=[]
 if not route: defects.append({'id':r.get('backend_request_id'),'reason':'missing router'});continue
 pe=byid.get(route.get('prefill_id','')+'-0',[]); de=byid.get(route.get('decode_id','')+'-0',[])
 pfirst=[e for e in pe if 'send_kv_caches_and_hidden_states' in e.get('host_intervals',{})]
 dfirst=[e for e in de if 'recv_kv_caches_and_hidden_states' in e.get('host_intervals',{})]
 if len(pfirst)!=1 or len(dfirst)!=1 or len(de)!=8: reasons.append('step mapping')
 if len(pfirst)==1 and len(dfirst)==1:
  pp=pfirst[0];dd=dfirst[0];pi=pp['host_intervals']['send_kv_caches_and_hidden_states'];di=dd['host_intervals']['recv_kv_caches_and_hidden_states']
  checks=[route['arrival_ns']<=route['prefill_submit_ns']<=pp['host_start_ns']<=pi[0]<=pi[1]<=pp['host_after_sync_ns']<=route['prefill_done_ns']<=route['decode_submit_ns']<=dd['host_start_ns']<=di[0]<=di[1]<=dd['host_after_sync_ns']<=route['decode_done_ns']<=route['router_complete_ns'], dd['host_intervals'].get('kv_bypass') is True, 'full_model_forward' not in dd['gpu_event_ms']]
  if not all(checks): reasons.append('boundary_or_bypass:'+str(checks))
  for phase,e,k in [('producer',pp,'send_kv_caches_and_hidden_states'),('consumer',dd,'recv_kv_caches_and_hidden_states')]:
   interval=e['host_intervals'][k]; key=(r['length'],r['batch'],phase,len(e['request_ids_to_seq_ids'])); eid=(e['pid'],e['host_start_ns'])
   if not r['warmup']: unique[key][eid]={'host_ms':(interval[1]-interval[0])/1e6,'gpu_event_ms':e['gpu_event_ms'][k+'_gpu']}
  pairs.append({'router_id':route['router_id'],'prefill_id':route['prefill_id'],'decode_id':route['decode_id'],'length':r['length'],'requested_batch':r['batch'],'wave':r['wave'],'warmup':r['warmup'],'prefill_actual_batch':len(pp['request_ids_to_seq_ids']),'decode_actual_batch':len(dd['request_ids_to_seq_ids']),'prefill_send_host_ns':pi,'decode_recv_install_host_ns':di,'arrival_ns':route['arrival_ns'],'complete_ns':route['router_complete_ns']})
 if reasons: defects.append({'id':r.get('backend_request_id'),'reason':reasons})
 counts[(r['length'],r['batch'],r['warmup'],not reasons)]+=1
summary=[]
for k,values in sorted(unique.items()):
 summary.append({'input_tokens':k[0],'requested_batch':k[1],'phase':k[2],'actual_batch':k[3],'distinct_steps':len(values),'host_median_ms':statistics.median(v['host_ms'] for v in values.values()),'gpu_event_median_ms':statistics.median(v['gpu_event_ms'] for v in values.values())})
res={'requests':len(requests),'status':dict(collections.Counter(str(x['status']) for x in requests)),'counts':[{'length':k[0],'requested_batch':k[1],'warmup':k[2],'valid':k[3],'n':v} for k,v in sorted(counts.items())],'defects':defects,'step_summaries':summary,'limits':'Profiler only: GPU event elapsed can include queue/host delays; host intervals enclose asynchronous work and are not additive GPU time. Consumer interval includes select wait and cache installation; it is not pure wire latency. Producer and consumer timings overlap communication and must not be summed. Distinct steps can still share a wave.'}
(p/'flow-audit.json').write_text(json.dumps(res,indent=2)+'\n');(p/'request-map.jsonl').write_text(''.join(json.dumps(x,separators=(',',':'))+'\n' for x in pairs));print(json.dumps(res,indent=2))
