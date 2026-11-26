"""Join diagnostic replay outputs to independent calibration; do not infer validity."""
import collections,csv,hashlib,json,math,pathlib,statistics,sys
p=pathlib.Path(sys.argv[1]);out=pathlib.Path(sys.argv[2]);out.mkdir(exist_ok=False);status=json.loads((p/'status.json').read_text());manifest=json.loads((p/'manifest.json').read_text())
if status['status']!='completed' or status['runs']!=12:raise ValueError('replay incomplete')
rows=[];errors=[]
for case in manifest['cases']:
 d=p/case['case'];mapping=json.loads((d/'request-map.json').read_text());trace=list(csv.DictReader((d/'trace.csv').open())); maps={str(x['simulator_request_id']):x for x in mapping}
 if len(maps)!=32 or len(trace)!=32:raise ValueError('mapping size mismatch')
 predictions={}
 for name in ('dag','adapted_baseline'):
  folder=d/name;files=list(folder.glob('*/plots/completed_at.csv'));arrivals=list(folder.glob('*/plots/arrived_at.csv'))
  if len(files)!=1 or len(arrivals)!=1:raise ValueError(f'ambiguous output {folder}')
  comp=list(csv.DictReader(files[0].open()));arr=list(csv.DictReader(arrivals[0].open()));ends={x['Request Id']:float(x['completed_at']) for x in comp};starts={x['Request Id']:float(x['arrived_at']) for x in arr}
  if set(ends)!=set(maps) or set(starts)!=set(maps) or len(comp)!=32 or len(arr)!=32:raise ValueError('simulator request IDs missing or duplicate')
  for k in maps:
   expected=float(trace[int(k)]['arrived_at'])
   if not math.isclose(starts[k],expected,abs_tol=1e-9):raise ValueError('simulator arrival differs from trace')
   if ends[k]<starts[k]:raise ValueError('negative predicted E2E')
  predictions[name]={k:ends[k]-starts[k] for k in maps}
 for k,r in maps.items():
  actual=r['server_e2e_s'];
  if actual<=0:raise ValueError('invalid measured duration')
  rows.append({'case':case['case'],'simulator_request_id':k,'router_id':r['router_id'],'server_e2e_s':actual,'dag_e2e_s':predictions['dag'][k],'adapted_baseline_e2e_s':predictions['adapted_baseline'][k],'dag_absolute_error_s':abs(predictions['dag'][k]-actual),'adapted_baseline_absolute_error_s':abs(predictions['adapted_baseline'][k]-actual)})
with (out/'requests.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
groups=collections.defaultdict(list)
for r in rows:groups[r['case']].append(r)
summary=[]
for case,rs in sorted(groups.items()):
 summary.append({'case':case,'requests':len(rs),'observed_median_s':statistics.median(x['server_e2e_s'] for x in rs),'dag_median_s':statistics.median(x['dag_e2e_s'] for x in rs),'adapted_baseline_median_s':statistics.median(x['adapted_baseline_e2e_s'] for x in rs),'dag_mean_absolute_error_s':statistics.mean(x['dag_absolute_error_s'] for x in rs),'adapted_baseline_mean_absolute_error_s':statistics.mean(x['adapted_baseline_absolute_error_s'] for x in rs)})
result={'status':'diagnostic_only','requests':len(rows),'cases':summary,'source_manifest_sha256':hashlib.sha256((p/'manifest.json').read_bytes()).hexdigest(),'limitations':['Candidate compute, CPU, transfer costs and device occupancy not frozen','Real router boundaries are not demonstrably equal to simulator boundaries','Adapted baseline is not the untouched original','A replayed arrival schedule does not reproduce real service batching','Calibrations show high variability and warmup KV idle is not proven','No hardware accuracy, improvement, or validation claim']}
(out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
