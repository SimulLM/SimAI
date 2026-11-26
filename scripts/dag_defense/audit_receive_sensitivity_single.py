"""Check replacement, equal fee and ordering in isolated diagnostic runs."""
import csv,json,math,pathlib,sys
root=pathlib.Path(sys.argv[1]);out=pathlib.Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=False)
status=json.loads((root/'status.json').read_text());assert all(x['exit']==0 for x in status['results']) and status['formal_validation'] is False
fee=json.loads((root/'fit-coefficients.json').read_text());expected=fee['intercept_s']+512*fee['per_input_token_s']
def read_one(folder):
 p=root/folder;dirs=list(p.glob('2026*'));assert len(dirs)==1
 with (dirs[0]/'request_metrics.csv').open() as f:rows=list(csv.DictReader(f))
 assert len(rows)==1 and 'Traceback' not in (p/'process.log').read_text() and 'Exception ignored' not in (p/'process.log').read_text();return dirs[0],rows[0]
d,dr=read_one('dag');b,br=read_one('baseline')
for r in (dr,br):
 assert float(r['request_num_prefill_tokens'])==512 and float(r['request_num_decode_tokens'])==64
 assert math.isclose(float(r['pd_p2p_comm_time']),expected,abs_tol=1e-12)
 assert math.isclose(float(r['decode_arrived_at'])-float(r['prefill_completed_at']),expected,abs_tol=1e-12)
assert math.isclose(float(dr['request_e2e_time']),float(br['request_e2e_time']),abs_tol=1e-10)
with (d/'timeline.csv').open() as f:timeline=list(csv.DictReader(f))
transfer=[x for x in timeline if x['task_id']=='transfer.0' and x['graph_id'].startswith('pd/')];first=[x for x in timeline if x['task_id']=='consumer.first_token'];assert len(transfer)==len(first)==1
assert math.isclose(float(transfer[0]['duration_s']),expected,abs_tol=1e-12) and float(transfer[0]['end_at_s'])<=float(first[0]['start_at_s'])
assert len({x['graph_id'] for x in timeline if x['graph_id'].startswith('replica1/')})==63
result={'status':'single_request_equal_fee_sensitivity_only','receiver_fee_s':expected,'dag_e2e_s':float(dr['request_e2e_time']),'adapted_baseline_e2e_s':float(br['request_e2e_time']),'transfer_tasks':len(transfer),'consumer_first_token_tasks':len(first),'later_decode_batches':63,'limitations':['Fit includes synchronization and waits; not a production fee','Baseline and DAG both adapted for this diagnostic, pristine baseline kept separately','Only single request; no concurrent resource equivalence or output boundary closure','No validation duration used to set parameters']};(out/'audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
