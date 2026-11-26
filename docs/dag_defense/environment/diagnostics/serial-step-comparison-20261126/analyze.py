import csv,glob,json,pathlib,statistics,collections
root=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/light-serial-512-20261126')
out=pathlib.Path(__file__).parent
clients=json.loads((root/'client.json').read_text()); assert len(clients)==25
workers=collections.defaultdict(list)
for f in (root/'service/events').glob('*.jsonl'):
 for line in f.open():
  e=json.loads(line)
  for g in e.get('groups',[]):workers[g['request_id']].append(e)
paths=glob.glob('/root/autodl-tmp/dag-handoff/runs/whole-forward-replay-20261126/dag/2026*/timeline.csv');assert len(paths)==1
sim=list(csv.DictReader(open(paths[0]))); initial=next(float(x['end_at_s']) for x in sim if x['task_id']=='consumer.first_token')
stages={}
for x in sim:
 if x['graph_id'].startswith('replica1/'):
  stages.setdefault(x['graph_id'],[]).append(x)
stages=sorted(stages.values(),key=lambda x:float(x[0]['start_at_s']));assert len(stages)==63
sim_ends=[max(float(x['end_at_s']) for x in s) for s in stages]
per=[]
for c in clients[5:]:
 assert c['done'] and c['usage']['completion_tokens']==64
 es=workers[c['backend_id']+'-0']; starts=sorted(e['timestamp_ns'] for e in es if e['event']=='model_step_host_start'); ends=sorted(e['timestamp_ns'] for e in es if e['event']=='model_step_host_return');assert len(starts)==len(ends)==64
 for i in range(63):
  real=(ends[i+1]-ends[0])/1e6;pred=(sim_ends[i]-initial)*1e3
  per.append({'request_id':c['router_id'],'iteration':i+1,'real_from_first_host_return_ms':real,'sim_from_first_task_end_ms':pred,'difference_ms':pred-real})
with (out/'per-request-iterations.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=per[0]);w.writeheader();w.writerows(per)
rows=[]
for i in range(1,64):
 a=[x for x in per if x['iteration']==i]; vals=sorted(x['difference_ms'] for x in a);rows.append({'iteration':i,'n':len(a),'sim_elapsed_ms':a[0]['sim_from_first_task_end_ms'],'real_elapsed_median_ms':statistics.median(x['real_from_first_host_return_ms'] for x in a),'difference_median_ms':statistics.median(vals),'difference_min_ms':min(vals),'difference_max_ms':max(vals)})
with (out/'by-iteration.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
print(json.dumps([rows[i] for i in (0,15,31,47,62)],indent=2))
