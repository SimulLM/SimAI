"""Join client collection to router monotonic boundaries; never infer missing timestamps."""
import argparse,collections,json,pathlib,sys

def reconcile(inputs,client_path,router_path,output):
 requests=[json.loads(x) for x in inputs.read_text().splitlines()];clients=collections.defaultdict(list);events=collections.defaultdict(lambda:collections.defaultdict(list))
 for line in client_path.read_text().splitlines():
  x=json.loads(line);clients[x['request_id']].append(x)
 for line in router_path.read_text().splitlines():
  x=json.loads(line);events[x['request_id']][x['event']].append(x)
 rows=[];errors=[];seen_router=set()
 for r in requests:
  matches=clients[r['request_id']];row={'run_id':r['run_id'],'request_id':r['request_id'],'input_id':r['input_id'],'input_sha256':r['input_sha256'],'wave':r['wave'],'status':'missing_client','error':'','server_arrival_ns':None,'server_complete_ns':None,'server_e2e_s':None}
  if len(matches)!=1:row['error']='expected exactly one client record';errors.append({'request_id':r['request_id'],'error':row['error']});rows.append(row);continue
  c=matches[0]
  if any(c.get(k)!=r.get(k) for k in ('run_id','request_id','input_id','input_sha256','wave')):errors.append({'request_id':r['request_id'],'error':'client/input identity mismatch'})
  row.update({k:c.get(k) for k in ('status','error','router_id','backend_request_id','scheduled_arrival_ns','client_send_ns','client_first_token_ns','client_complete_ns','http_status','usage')});rid=c.get('router_id')
  if not rid:
   if c['status']=='success':errors.append({'request_id':r['request_id'],'error':'missing router ID'})
   rows.append(row);continue
  if rid in seen_router:errors.append({'request_id':r['request_id'],'error':'duplicate router ID'})
  seen_router.add(rid);ev=events[rid];arrival=ev['server_arrival'];complete=ev['server_complete'];mapping=ev['decode_mapping']
  if len(arrival)==1:row['server_arrival_ns']=arrival[0]['timestamp_ns']
  if len(complete)==1:row['server_complete_ns']=complete[0]['timestamp_ns']
  if row['server_arrival_ns'] is not None and row['server_complete_ns'] is not None:row['server_e2e_s']=(row['server_complete_ns']-row['server_arrival_ns'])/1e9
  if c['status']=='success':
   problems=[]
   ordered=('server_arrival','prefill_send','prefill_response','prefill_mapping','decode_send','decode_mapping','server_first_token','server_complete')
   if any(len(ev[name])!=1 for name in ordered):problems.append('missing or duplicate required server event')
   elif any(ev[name][0].get('clock_id')!='CLOCK_MONOTONIC' for name in ordered):problems.append('clock mismatch')
   elif any(ev[a][0]['timestamp_ns']>ev[b][0]['timestamp_ns'] for a,b in zip(ordered,ordered[1:])):problems.append('server event order mismatch')
   elif ev['prefill_response'][0].get('status')!=200 or ev['server_error']:problems.append('server error or prefill failure')
   elif complete[0].get('usage')!=c.get('usage'):problems.append('completion usage mismatch')
   if len(arrival)!=1 or len(complete)!=1 or len(mapping)!=1:problems.append('missing or duplicate server boundaries/mapping')
   elif row['server_e2e_s']<0 or mapping[0].get('backend_request_id')!=c.get('backend_request_id'):problems.append('server clock order or backend ID mismatch')
   elif any(x.get('clock_id')!='CLOCK_MONOTONIC' for x in (arrival[0],complete[0],mapping[0])):problems.append('clock mismatch')
   if problems:errors.append({'request_id':r['request_id'],'error':'; '.join(problems)})
  rows.append(row)
 expected={r['request_id'] for r in requests}
 if len(expected)!=len(requests):errors.append({'error':'duplicate input request IDs'})
 extra=set(clients)-expected
 if extra:errors.append({'error':'unexpected client IDs','ids':sorted(extra)})
 output.mkdir(parents=True,exist_ok=False)
 with (output/'requests.jsonl').open('w') as f:
  for r in rows:f.write(json.dumps(r,separators=(',',':'))+'\n')
 counts=dict(collections.Counter(x['status'] for x in rows));status='complete' if len(rows)==32 and counts=={'success':32} and not errors else 'incomplete';summary={'status':status,'request_count':len(rows),'status_counts':counts,'errors':errors,'clock_id':'CLOCK_MONOTONIC','metric':'server_complete_ns - server_arrival_ns','limitations':['router completion is stream completion, not GPU completion','separate pre-run idle evidence and frozen configuration verification remain required','incomplete or failed rows must be retained; no missing server timestamp is fabricated']};(output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');return summary
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--inputs',type=pathlib.Path,required=True);p.add_argument('--client',type=pathlib.Path,required=True);p.add_argument('--router',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args();r=reconcile(a.inputs,a.client,a.router,a.output);print(json.dumps(r,indent=2));sys.exit(0 if r['status']=='complete' else 1)
