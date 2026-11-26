"""Reanalyze independent synchronized receiver intervals without adding overlap."""
import collections,csv,json,math,pathlib,statistics,sys
root=pathlib.Path(sys.argv[1]);out=pathlib.Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=False)
assert (root/'exit').read_text().strip()=='0';requests=[json.loads(x) for x in (root/'client.jsonl').read_text().splitlines()];assert len(requests)==120
router=collections.defaultdict(dict)
for line in (root/'service/router-events.jsonl').read_text().splitlines():
 e=json.loads(line);assert e['event'] not in router[e['request_id']];router[e['request_id']][e['event']]=e
steps=collections.defaultdict(list)
for f in (root/'service/events').glob('*.jsonl'):
 for line in f.read_text().splitlines():
  e=json.loads(line)
  if e.get('role')=='consumer' and e.get('step_id'):
   for g in e.get('groups',[]):steps[(g['request_id'],e['step_id'])].append(e)
rows=[]
for r in requests:
 assert r['status']==200 and r['done'] and r['usage']['prompt_tokens']==r['length'] and r['usage']['completion_tokens']==8
 ev=router[r['router_id']];rid=ev['decode_mapping']['backend_request_id']+'-0';assert rid==r['backend_id']+'-0'
 matches=[v for (req,step),v in steps.items() if req==rid and any(x['event']=='kv_install_sync_complete' for x in v)];assert len(matches)==1;v=matches[0]
 def at(name):
  x=[e['timestamp_ns'] for e in v if e['event']==name];assert len(x)==1,(name,len(x));return x[0]
 start=at('recv_kv_caches_and_hidden_states_host_start');recv=at('recv_kv_caches_and_hidden_states_host_return');sync=at('kv_install_sync_complete');end=at('model_step_host_return');installs=sorted(e['timestamp_ns'] for e in v if e['event']=='kv_install_api_start');assert len(installs)==32 and start<=installs[0]<=installs[-1]<=recv<=sync<=end
 rows.append({'length':r['length'],'wave':r['wave'],'warmup':r['warmup'],'router_id':r['router_id'],'decode_id':rid,'receive_start_ns':start,'first_install_ns':installs[0],'receive_return_ns':recv,'install_sync_ns':sync,'step_return_ns':end,'receive_to_install_sync_ms':(sync-start)/1e6,'install_to_sync_ms':(sync-installs[0])/1e6,'post_sync_host_return_ms':(end-sync)/1e6})
with (out/'samples.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
groups=[]
for length in (512,1024,2048):
 warm=[x for x in rows if x['length']==length and x['warmup']];measured=[x for x in rows if x['length']==length and not x['warmup']];assert len(warm)==10 and len(measured)==30
 stats={}
 for key in ('receive_to_install_sync_ms','install_to_sync_ms','post_sync_host_return_ms'):
  vals=sorted(x[key] for x in measured);stats[key]={'median_ms':statistics.median(vals),'min_ms':vals[0],'max_ms':vals[-1],'p95_ms':vals[math.ceil(len(vals)*.95)-1]}
 groups.append({'input_tokens':length,'warmup':10,'measured':30,'metrics':stats})
summary={'status':'inclusive_receiver_diagnostic_not_frozen','groups':groups,'limitations':['Receive-to-install-sync is an inclusive host interval containing waits, transport, installation, Python and added synchronization','Installation interval is a subset of receive interval and must not be added to it','Post-sync host return is a separate subsequent host boundary but does not include all router/scheduler work','Per-tensor device synchronization perturbs execution; serial output-8 only','Not a validated common physical cost or formal validation']};(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
