import argparse,csv,json,statistics
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('run',type=Path);a=p.parse_args();r=a.run
assert json.loads((r/'exit-codes.json').read_text())==[0,0]
summary=[]
for rank in (0,1):
 rows=list(csv.DictReader((r/f'rank{rank}.csv').open())); assert len(rows)==120
 for n in (512,1024,2048):
  group=[x for x in rows if int(x['tokens'])==n];assert len(group)==40 and [int(x['iteration']) for x in group]==list(range(40))
  assert all(int(x['warmup'])==(int(x['iteration'])<10) and int(x['kv_bytes'])==n*524288 and int(x['hidden_bytes'])==n*8192 and int(x['end_ns'])>=int(x['start_ns']) and abs(float(x['duration_s'])-(int(x['end_ns'])-int(x['start_ns']))/1e9)<1e-12 for x in group)
  samples=sorted(float(x['duration_s']) for x in group if x['warmup']=='0')
  summary.append(dict(rank=rank,tokens=n,n=len(samples),min_s=min(samples),median_s=statistics.median(samples),p95_s=samples[28],max_s=max(samples)))
with (r/'summary.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=summary[0]);w.writeheader();w.writerows(summary)
print('PASS: 2 ranks, 3 shapes, 10 warmup and 30 measured samples each; elapsed time and byte fields verified')
for row in summary: print(row)
