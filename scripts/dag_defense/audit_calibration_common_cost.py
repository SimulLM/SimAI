"""Check identical configured inputs and generated prediction tables in replay."""
import hashlib,json,pathlib,sys
p=pathlib.Path(sys.argv[1]); flags=['--replica_config_pd_p2p_comm_bandwidth','--random_forrest_execution_time_predictor_config_compute_input_file','--random_forrest_execution_time_predictor_config_attention_input_file','--random_forrest_execution_time_predictor_config_cpu_overhead_input_file','--random_forrest_execution_time_predictor_config_send_recv_input_file','--random_forrest_execution_time_predictor_config_all_reduce_input_file','--trace_request_generator_config_trace_file']; sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest();out=[]
for case in sorted(x for x in p.iterdir() if (x/'request-map.json').exists()):
 commands={n:json.loads((case/n/'command.json').read_text()) for n in ('dag','adapted_baseline')};values={}
 for flag in flags:
  a,b=(commands[n][commands[n].index(flag)+1] for n in ('dag','adapted_baseline'))
  if a!=b:raise ValueError(f'different {flag} in {case.name}')
  values[flag]=a
 if values[flags[0]]!='255':raise ValueError('unexpected bandwidth')
 tables=[{f.name:sha(f) for f in (case/n/'cache').glob('*predictions.csv')} for n in ('dag','adapted_baseline')]
 if not tables[0] or tables[0]!=tables[1]:raise ValueError(f'different prediction tables in {case.name}')
 out.append({'case':case.name,'matching_prediction_tables':len(tables[0]),'table_sha256':tables[0],'matched_arguments':values})
if len(out)!=6:raise ValueError('expected six cases')
print(json.dumps({'status':'matched_config_and_prediction_tables','cases':out,'limitations':['Same prediction tables and configured transfer bandwidth do not prove identical actual batch costs when scheduling differs','Direct profile lookups and receive ordering still require separate validation','Adapted baseline is not pristine original','Diagnostic candidates are not frozen']},indent=2))
