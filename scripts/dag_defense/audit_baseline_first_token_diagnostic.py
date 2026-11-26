"""Compare single-request first-token diagnostic across DAG and adapted baseline."""
import csv,json,math,pathlib,sys
baseline=pathlib.Path(sys.argv[1]);dag=pathlib.Path(sys.argv[2]);old=pathlib.Path(sys.argv[3]);out=pathlib.Path(sys.argv[4]);out.mkdir(parents=True,exist_ok=False)
def one(p):
 dirs=list(p.glob('2026*'));assert len(dirs)==1
 with (dirs[0]/'request_metrics.csv').open() as f:r=list(csv.DictReader(f))
 assert len(r)==1;return r[0]
assert (baseline/'exit').read_text().strip()=='0' and (dag/'exit').read_text().strip()=='0'
log=(baseline/'process.log').read_text();assert 'Traceback' not in log and 'Exception ignored' not in log
bs=one(baseline);ds=one(dag);os=one(old);events=[json.loads(x) for x in (baseline/'first-token-events.jsonl').read_text().splitlines()];assert len(events)==1;e=events[0];cfg=json.loads((dag/'candidate-config.json').read_text());fee=cfg['consumer_first_token_host_s'];assert e['event_type']=='consumer_first_token_diagnostic' and e['replica_id']==1 and e['request_id']==0
assert all(float(r['request_num_prefill_tokens'])==512 and float(r['request_num_decode_tokens'])==64 for r in (bs,ds,os))
assert math.isclose(e['time'],float(bs['decode_arrived_at']),abs_tol=1e-12) and math.isclose(e['duration_s'],fee,abs_tol=1e-12) and math.isclose(e['end_s'],e['time']+fee,abs_tol=1e-12)
assert math.isclose(float(bs['completed_at'])-float(os['completed_at']),fee,abs_tol=1e-10)
assert math.isclose(float(bs['completed_at']),float(ds['completed_at']),abs_tol=1e-10)
result={'status':'single_request_equal_fee_mechanism_diagnostic','input_tokens':512,'output_tokens':64,'first_token_fee_s':fee,'baseline_event':e,'baseline_e2e_s':float(bs['request_e2e_time']),'dag_e2e_s':float(ds['request_e2e_time']),'unmodified_adapted_baseline_e2e_s':float(os['request_e2e_time']),'limitations':['Adapted diagnostic baseline includes predictor and serial first-token changes; pristine original preserved separately','Baseline event does not schedule a GPU resource; valid only in this enforced single-request diagnostic','Synchronized host interval is a sensitivity fee, not a frozen noninstrumented physical cost','Does not establish concurrent scheduling or production-accuracy improvement']}
(out/'audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
