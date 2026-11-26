"""Check isolated candidate first-token event and exactly-once accounting."""
import csv,json,math,pathlib,sys
root=pathlib.Path(sys.argv[1]);baseline=pathlib.Path(sys.argv[2]);out=pathlib.Path(sys.argv[3]);out.mkdir(parents=True,exist_ok=False)
def directory(p):
 ds=list(p.glob('2026*'));assert len(ds)==1;return ds[0]
def csvrows(p):
 with p.open() as f:return list(csv.DictReader(f))
d=directory(root);b=directory(baseline);assert (root/'exit').read_text().strip()=='0'
t=csvrows(d/'timeline.csv');tasks=[x for x in t if x['task_id']=='consumer.first_token'];assert len(tasks)==1
x=tasks[0];transfer=csvrows(d/'pd-transfers.csv');assert len(transfer)==1;kv=float(transfer[0]['kv_ready_at_s']);decode=float(transfer[0]['first_decode_start_s']);start=float(x['start_at_s']);end=float(x['end_at_s']);cfg=json.loads((root/'candidate-config.json').read_text());cost=cfg['consumer_first_token_host_s']
assert x['state']=='COMPLETED' and math.isclose(start,kv,abs_tol=1e-12) and math.isclose(end,decode,abs_tol=1e-12) and math.isclose(end-start,cost,abs_tol=1e-12)
resources=json.loads(x['demands']);assert any(v['resource_id']=='gpu:1:0:0' for v in resources)
def metrics(p):
 rows=csvrows(p/'request_metrics.csv');assert len(rows)==1 and float(rows[0]['request_num_prefill_tokens'])==512 and float(rows[0]['request_num_decode_tokens'])==64;return rows[0]
new=metrics(d);old=metrics(b);delta=float(new['request_e2e_time'])-float(old['request_e2e_time']);assert math.isclose(delta,cost,abs_tol=1e-10)
for path in (d,b):
 rows=csvrows(path/'timeline.csv');decode_graphs={r['graph_id'] for r in rows if r['graph_id'].startswith('replica1/')};assert len(decode_graphs)==63
result={'status':'single_request_mechanism_sensitivity_pass','candidate_cost_s':cost,'kv_ready_s':kv,'first_token_start_s':start,'first_token_end_s':end,'later_decode_start_s':decode,'later_decode_batches':63,'old_e2e_s':float(old['request_e2e_time']),'new_e2e_s':float(new['request_e2e_time']),'delta_s':delta,'limitations':['DAG candidate only; adapted or pristine baseline has not been given this stage','Serial-only host interval with inserted device synchronization; not a frozen physical fee','Concurrency and CPU/GPU resource overlap are not modeled by this single-request diagnostic','No validation data or request E2E was used to set fee']}
(out/'audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
