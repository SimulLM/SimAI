import csv,hashlib,json,pathlib,subprocess
root=pathlib.Path('/root/autodl-tmp/dag-handoff/runs');p=root/'controlled-2048-pristine-20261126/four_simultaneous';q=root/'controlled-2048-shared-fees-20261126/four_simultaneous/dag';repo=pathlib.Path('/root/autodl-tmp/SimAI-pristine-baseline');out=pathlib.Path(__file__).parent
assert subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()=='cef83f9ddd96540e3e9f48934f11335d52d54fce';assert subprocess.run(['git','-C',str(repo),'diff','--quiet']).returncode==0 and subprocess.run(['git','-C',str(repo),'diff','--cached','--quiet']).returncode==0
commands={name:json.loads((folder/'command.json').read_text()) for name,folder in [('pristine',p),('dag',q)]}
flags=['--random_forrest_execution_time_predictor_config_compute_input_file','--random_forrest_execution_time_predictor_config_attention_input_file','--random_forrest_execution_time_predictor_config_send_recv_input_file','--random_forrest_execution_time_predictor_config_all_reduce_input_file','--random_forrest_execution_time_predictor_config_cpu_overhead_input_file','--replica_config_pd_p2p_comm_bandwidth','--trace_request_generator_config_trace_file']
common={}
for flag in flags:
 vals={name:[cmd[i+1] for i,x in enumerate(cmd) if x==flag] for name,cmd in commands.items()};assert len(vals['pristine'])==len(vals['dag'])==1 and vals['pristine']==vals['dag'];v=vals['pristine'][0];entry={'value':v}
 if flag.endswith('input_file') or flag.endswith('trace_file'):entry['sha256']=hashlib.sha256(pathlib.Path(v).read_bytes()).hexdigest()
 common[flag]=entry
predictors=[repo/'vidur-alibabacloud/vidur/execution_time_predictor/sklearn_execution_time_predictor.py',pathlib.Path('/root/autodl-tmp/SimAI-pristine-predictor-repro/vidur-alibabacloud/vidur/execution_time_predictor/sklearn_execution_time_predictor.py')];h=[hashlib.sha256(x.read_bytes()).hexdigest() for x in predictors];assert h[0]==h[1]
metrics={}
for name,folder in [('pristine',p),('dag',q)]:
 d=next(folder.glob('2026*'));rows={str(int(x['Request Id'])):x for x in csv.DictReader((d/'request_metrics.csv').open())};assert set(rows)==set('0123');assert all(float(x['request_num_prefill_tokens'])==2048 and float(x['request_num_decode_tokens'])==128 for x in rows.values());metrics[name]=rows
records=[]
dagdir=next(q.glob('2026*'));transfers={str(x['request_id']):x for x in csv.DictReader((dagdir/'pd-transfers.csv').open())};timeline=list(csv.DictReader((dagdir/'timeline.csv').open()));assert len(transfers)==4
for rid in '0123':
 a,b=metrics['pristine'][rid],metrics['dag'][rid];payload=int(float(a['pd_p2p_comm_size']));wire=int(b['pd_p2p_comm_size']);assert payload-wire==524288 and wire==int(transfers[rid]['wire_bytes']);base=float(a['pd_p2p_comm_time']);expected=payload/(255*1024**3/8);assert abs(base-expected)<1e-12
 task=[x for x in timeline if x['graph_id']==f'pd/{rid}/stage0/migration0' and x['task_id']=='transfer.0'];assert len(task)==1 and abs(float(task[0]['duration_s'])-base)<1e-12
 records.append({'request_id':rid,'pristine_billing_bytes':payload,'dag_reported_wire_bytes':wire,'common_transfer_task_s':base,'dag_elapsed_prefill_to_ready_s':float(b['pd_p2p_comm_time']),'dag_elapsed_excess_over_task_s':float(b['pd_p2p_comm_time'])-base})
first=[json.loads(x) for x in (q/'first-token.jsonl').open()];submit=[x for x in first if x['event']=='submit'];assert sum(len(x['request_ids']) for x in submit)==4
assert not list(next(p.glob('2026*')).glob('timeline.csv'))
result={'status':'incomplete_common_physical_contract','baseline_commit':'cef83f9ddd96540e3e9f48934f11335d52d54fce','predictor_sha256':h[0],'shared_inputs':common,'transfer_records':records,'dag_first_token_tasks':submit,'pristine_consumer_first_token_tasks':0,'limitations':['DAG elapsed transfer includes modeled resource waits; compare base fee not elapsed time','common profile hash does not prove additive physical scopes','original predictor missing separately modeled consumer first token','255 Gibit/s includes hidden transfer in fitted scope; do not charge hidden bytes again','model communication does not include measured paged KV installation','CPU synchronized sampler can include GPU work and must not be paired with a separate identical sampler fee','no validation duration used to fit costs']};(out/'audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
