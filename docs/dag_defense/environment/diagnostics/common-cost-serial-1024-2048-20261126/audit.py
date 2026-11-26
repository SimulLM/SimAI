import csv,json,pathlib,collections,math
base=pathlib.Path(__file__).parent;out={}
for n in (1024,2048):
 p=base/str(n);d=p/'dag';b=p/'baseline';assert (d/'exit').read_text().strip()==(b/'exit').read_text().strip()=='0'
 cost=json.loads((d/'cost-encoding.json').read_text());bc=json.loads((b/'cost-encoding.json').read_text());assert cost==bc
 dr=next(d.glob('2026*'));br=next(b.glob('2026*'));dm=list(csv.DictReader((dr/'request_metrics.csv').open()));bm=list(csv.DictReader((br/'request_metrics.csv').open()));assert len(dm)==len(bm)==1
 # Adapted baseline and DAG model identical serial scope for this candidate only.
 differences={k:abs(float(dm[0][k])-float(bm[0][k])) for k in ('request_e2e_time','request_model_execution_time','pd_p2p_comm_time')};assert max(differences.values())<1e-9
 trans=list(csv.DictReader((dr/'pd-transfers.csv').open()));assert len(trans)==1;tr=trans[0];assert tr['state']=='COMPLETED' and abs(float(tr['transfer_completed_at_s'])-float(tr['transfer_started_at_s'])-cost['receive_s'])<1e-9
 ts=list(csv.DictReader((dr/'timeline.csv').open()));ft=[x for x in ts if x['task_id']=='consumer.first_token'];assert len(ft)==1 and abs(float(ft[0]['duration_s'])-cost['first_s'])<1e-12 and float(tr['kv_ready_at_s'])<=float(ft[0]['start_at_s'])<=float(ft[0]['end_at_s'])<=float(tr['first_decode_start_s'])
 stages=collections.defaultdict(list)
 for t in ts:
  if t['graph_id'].startswith('replica'):stages[t['graph_id']].append(t)
 assert len(stages)==128
 for graph,tasks in stages.items():assert sum(t['task_id']=='cpu.finish' for t in tasks)==1
 graph_counts={'prefill':sum('replica0/' in g for g in stages),'decode':sum('replica1/' in g for g in stages)};assert graph_counts=={'prefill':1,'decode':127}
 be=[json.loads(x) for x in (b/'first-token-events.jsonl').read_text().splitlines()];assert len(be)==1 and abs(be[0]['duration_s']-cost['first_s'])<1e-12
 out[str(n)]={'baseline':'predictor-adapted and serial first-token modified','prefill':1,'decode':127,'receive_tasks':1,'consumer_first_token_tasks':1,'receive_s':cost['receive_s'],'post_sync_s':cost['first_s'],'max_metric_difference_s':max(differences.values()),'graph_counts':graph_counts}
(base/'audit.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
