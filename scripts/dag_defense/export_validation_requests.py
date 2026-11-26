"""Export reconciled records with explicit missing fields and clock semantics."""
import argparse,csv,json,pathlib
if not __debug__:raise RuntimeError("optimized Python disables required checks")
FIELDS=('run_id','request_id','input_id','status','error','scheduled_arrival_s','client_send_s','client_first_token_s','client_complete_s','server_arrival_s','server_final_choice_s','server_complete_s','server_final_choice_to_complete_s','actual_input_tokens','actual_output_tokens','server_e2e_s','client_e2e_s','client_ttft_s','client_tpot_s')
TIMES={'scheduled_arrival_s':'scheduled_arrival_ns','client_send_s':'client_send_ns','client_first_token_s':'client_first_token_ns','client_complete_s':'client_complete_ns','server_arrival_s':'server_arrival_ns','server_final_choice_s':'server_final_choice_ns','server_complete_s':'server_complete_ns'}
def export(reconciled,spec_file,out):
 spec=json.loads(spec_file.read_text());origin=spec['origin_ns'];assert spec['clock_id']=='CLOCK_MONOTONIC' and isinstance(origin,int) and origin>=0
 rows=[json.loads(x) for x in reconciled.read_text().splitlines() if x.strip()];assert len(rows)==32 and len({x['request_id'] for x in rows})==32
 assert len({x['run_id'] for x in rows})==1,'mixed run IDs'
 if spec.get('spec',{}).get('run_id') is not None:assert rows[0]['run_id']==spec['spec']['run_id'],'run ID mismatch'
 output=[];missing=[]
 for item in rows:
  row={k:item.get(k) for k in ('run_id','request_id','input_id','status','error')};row['error']=row['error'] or ''
  assert all(row[x] for x in ('run_id','request_id','input_id','status'))
  for field,key in TIMES.items():
   value=item.get(key)
   if value is None:row[field]=None
   else:
    assert isinstance(value,int) and value>=origin,(row['request_id'],field)
    row[field]=(value-origin)/1e9
  usage=item.get('usage') or {};row['actual_input_tokens']=usage.get('prompt_tokens');row['actual_output_tokens']=usage.get('completion_tokens')
  for a,b in (('client_send_s','client_first_token_s'),('client_first_token_s','client_complete_s'),('server_arrival_s','server_final_choice_s'),('server_final_choice_s','server_complete_s'),('server_arrival_s','server_complete_s')):
   if row[a] is not None and row[b] is not None:assert row[a]<=row[b],(row['request_id'],a,b)
  def difference(a,b):return None if row[a] is None or row[b] is None else row[b]-row[a]
  row['server_final_choice_to_complete_s']=difference('server_final_choice_s','server_complete_s')
  row['server_e2e_s']=difference('server_arrival_s','server_complete_s');row['client_e2e_s']=difference('client_send_s','client_complete_s');row['client_ttft_s']=difference('client_send_s','client_first_token_s')
  n=row['actual_output_tokens'];elapsed=difference('client_first_token_s','client_complete_s');row['client_tpot_s']=elapsed/(n-1) if isinstance(n,int) and n>1 and elapsed is not None else None
  for field in FIELDS:
   if row.get(field) is None:missing.append({'request_id':row['request_id'],'field':field,'reason':'not recorded or not applicable; status='+row['status']})
  output.append(row)
 out.mkdir(parents=True,exist_ok=False)
 with (out/'requests.csv').open('w',newline='',encoding='utf8') as f:
  w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(output)
 (out/'missing-fields.json').write_text(json.dumps({'missing':missing,'clock_id':'CLOCK_MONOTONIC','origin_ns':origin,'definitions':{'server_final_choice_to_complete_s':'router stream completion minus observation of final choice; not GPU completion','server_e2e_s':'server_complete_s - server_arrival_s','client_e2e_s':'client_complete_s - client_send_s','client_ttft_s':'client_first_token_s - client_send_s','client_tpot_s':'(client_complete_s - client_first_token_s) / (actual_output_tokens - 1)','client_complete':'response stream consumed including terminal marker and end of stream','server_complete':'router received and forwarded complete response stream; not GPU completion'}},indent=2)+'\n')
 return {'rows':len(output),'missing_fields':len(missing),'status_counts':{k:sum(r['status']==k for r in output) for k in sorted({r['status'] for r in output})}}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--reconciled',type=pathlib.Path,required=True);p.add_argument('--run-spec',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args();print(json.dumps(export(a.reconciled,a.run_spec,a.output),indent=2))
