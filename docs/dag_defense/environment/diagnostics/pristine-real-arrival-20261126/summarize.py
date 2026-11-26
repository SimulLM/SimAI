import csv,glob,json,pathlib,statistics,hashlib
root=pathlib.Path(__file__).parent;old=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/pd-pull-calibration-replay-20261126')
rows=[]
for case in ('serial-0','concurrent-0'):
 mapping=json.loads((old/case/'request-map.json').read_text());assert len(mapping)==32
 def get(mode):
  p=root/case/mode;assert (p/'exit').read_text().strip()=='0'; files=list(p.glob('2026*/request_metrics.csv'));assert len(files)==1
  data={int(x['Request Id']):x for x in csv.DictReader(files[0].open())};assert len(data)==32;return data
 d,b=get('dag'),get('baseline')
 for x in mapping:
  i=x['simulator_request_id'];real=x['server_e2e_s'];assert real>0
  dp=float(d[i]['request_e2e_time']);bp=float(b[i]['request_e2e_time'])
  rows.append(dict(case=case,request_id=i,router_id=x['router_id'],real_s=real,dag_s=dp,baseline_s=bp,dag_abs_error_s=abs(dp-real),baseline_abs_error_s=abs(bp-real)))
with (root/'comparison.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
summary={}
for case in ('serial-0','concurrent-0'):
 a=[x for x in rows if x['case']==case]
 summary[case]={'requests':len(a),'real_median_s':statistics.median(x['real_s'] for x in a),'dag_mae_s':statistics.mean(x['dag_abs_error_s'] for x in a),'baseline_mae_s':statistics.mean(x['baseline_abs_error_s'] for x in a)}
(root/'comparison.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
