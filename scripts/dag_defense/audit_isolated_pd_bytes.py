"""Trace the isolated candidate's reported and charged PD bytes."""
import csv,hashlib,json,math,pathlib,sys
root=pathlib.Path(sys.argv[1]);out=pathlib.Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=False)
def result(version):
 dirs=list((root/version).glob('2026*'));assert len(dirs)==1
 with (dirs[0]/'request_metrics.csv').open() as f: rows=list(csv.DictReader(f))
 assert len(rows)==1 and rows[0]['Request Id']=='0';return dirs[0],rows[0]
dag,dr=result('dag');base,br=result('adapted_baseline');graphs=list((dag/'graphs').glob('pd-*.graph.json'));assert len(graphs)==1
graph=json.loads(graphs[0].read_text()); task=next(x for x in graph['tasks'] if x['task_id']=='transfer.0'); meta=task['metadata'];n=int(float(dr['request_num_prefill_tokens'])); per_token=2*32*32*128*2
assert n==512 and per_token==524288 and meta['wire_bytes']==n*per_token and meta['billing_bytes']==(n+1)*per_token
assert int(float(br['pd_p2p_comm_size']))==meta['billing_bytes'] and int(float(dr['pd_p2p_comm_size']))==meta['wire_bytes']
assert meta['billing_basis']=='legacy_prefill_plus_one' and math.isclose(task['cost']['duration_s'],float(br['pd_p2p_comm_time']),rel_tol=1e-12)
assert math.isclose(task['cost']['duration_s'],meta['billing_bytes']/meta['bandwidth_bytes_per_s'],rel_tol=1e-12)
result={'status':'candidate_charging_equal_for_this_request','input_tokens':n,'kv_bytes_per_token':per_token,'dag_reported_kv_wire_bytes':meta['wire_bytes'],'dag_billing_bytes':meta['billing_bytes'],'baseline_reported_and_billing_bytes':int(float(br['pd_p2p_comm_size'])),'billing_bandwidth_bytes_per_s':meta['bandwidth_bytes_per_s'],'charge_seconds':task['cost']['duration_s'],'extra_billing_bytes':per_token,'dag_graph_sha256':hashlib.sha256(graphs[0].read_bytes()).hexdigest(),'limits':['Reported KV wire bytes omit hidden-state and connector control bytes; do not interpret as complete real traffic','The common 255 Gibit/s candidate is an effective fit to a KV-plus-hidden transfer microbenchmark and is not a raw physical link rate','Same charge for this shape does not prove physical cost accuracy, all batch shapes, no double counting, or first-token equivalence','Adapted baseline is not the pristine original; not a frozen validation']}
(out/'audit.json').write_text(json.dumps(result,indent=2)+'\n');(out/'dag-transfer-graph.json').write_text(json.dumps(graph,indent=2)+'\n');print(json.dumps(result,indent=2))
