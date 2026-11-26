import csv,json,pathlib
base=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/batch-first-token-mechanism-v2-20261126');out={}
for case,count,cost in [('simultaneous2',2,.0015),('simultaneous4',4,.002)]:
 p=base/case;assert (p/'exit').read_text().strip()=='0';events=[json.loads(x) for x in (p/'first-token.jsonl').read_text().splitlines()];assert len(events)==2
 start,end=events;assert start['event']=='submit' and end['event']=='complete' and start['request_ids']==end['request_ids']==[str(x) for x in range(count)] and start['cost_s']==cost
 root=next(p.glob('2026*'))
 with (root/'pd-transfers.csv').open() as f:requests=list(csv.DictReader(f))
 assert len(requests)==count
 for r in requests:assert r['state']=='COMPLETED' and float(r['kv_ready_at_s'])<=start['time_s']<=end['time_s']<=float(r['first_decode_start_s']) and int(r['source_reservations'])==int(r['destination_reservations'])==int(r['pins'])==0
 with (root/'timeline.csv').open() as f:tasks=[x for x in csv.DictReader(f) if x['graph_id']==start['graph_id'] and x['task_id']=='consumer.first_token.batch']
 assert len(tasks)==1 and abs(float(tasks[0]['duration_s'])-cost)<1e-12 and abs(float(tasks[0]['end_at_s'])-end['time_s'])<1e-12
 out[case]={'requests':count,'shared_tasks':len(tasks),'all_kv_ready_before_submit':True,'decode_after_task':True,'all_released':True,'cost_s':cost}
pathlib.Path(__file__).with_name('audit.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
missing=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/batch-first-token-missing-cost-20261126/simultaneous4');assert (missing/'exit').read_text().strip()=='1';assert 'unmeasured first-token batch 512:4' in (missing/'process.log').read_text();print('PASS missing cost rejected')
