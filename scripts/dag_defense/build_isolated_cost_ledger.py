"""Summarize candidate task costs by execution stage; no physical claims."""
import collections,csv,json,pathlib,sys
source=pathlib.Path(sys.argv[1]);out=pathlib.Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=False)
totals=collections.defaultdict(float);counts=collections.Counter()
for row in csv.DictReader(source.open()):
 graph=row['graph_id'];stage='prefill' if graph.startswith('replica0/') else 'decode' if graph.startswith('replica1/') else 'transfer' if graph.startswith('pd/') else None
 if stage is None:raise ValueError('unknown graph '+graph)
 key=(stage,row['kind'],row['op']);totals[key]+=float(row['duration_s']);counts[key]+=1
rows=[{'stage':k[0],'kind':k[1],'op':k[2],'tasks':counts[k],'sum_seconds':v} for k,v in sorted(totals.items())]
with (out/'task-cost-sums.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
(out/'summary.json').write_text(json.dumps({'status':'candidate_accounting_not_validated','source':str(source),'task_seconds_sum':sum(totals.values()),'rows':rows,'limitations':['Task work totals are not additive to elapsed time when resources overlap','Sampler host timings can include GPU waiting; not additive with CUDA timings','Consumer KV-bypass first-token stage is absent','Resource wait, routing and host/backend boundaries are not fully represented','Adapted baseline comparison is diagnostic, not original-baseline acceptance']},indent=2)+'\n')
