"""Compare replayed open-loop in-flight counts to recorded calibration service."""
import collections,csv,json,pathlib,statistics,sys
root=pathlib.Path(sys.argv[1]);dest=pathlib.Path(sys.argv[2]);dest.mkdir(exist_ok=False);rows=[];groups=[]
for case in sorted(x for x in root.iterdir() if (x/'request-map.json').exists()):
 mapping=json.loads((case/'request-map.json').read_text());origin=min(r['server_arrival_ns'] for r in mapping);ids={str(r['simulator_request_id']):r for r in mapping};pred={}
 for name in ('dag','adapted_baseline'):
  files=list((case/name).glob('*/plots/completed_at.csv'))
  if len(files)!=1:raise ValueError('missing/ambiguous completion file')
  raw=list(csv.DictReader(files[0].open()));pred[name]={r['Request Id']:float(r['completed_at']) for r in raw}
  if len(raw)!=len(ids) or set(pred[name])!=set(ids):raise ValueError('request identity mismatch')
 for r in mapping:
  rid=str(r['simulator_request_id']);now=(r['server_arrival_ns']-origin)/1e9;previous=[q for q in mapping if q['simulator_request_id']<r['simulator_request_id']]
  if any(q['server_arrival_ns']>r['server_arrival_ns'] for q in previous):raise ValueError('unordered input')
  actual=sum(q['server_complete_ns']>r['server_arrival_ns'] for q in previous)
  row={'case':case.name,'request_id':rid,'router_id':r['router_id'],'actual_previous_inflight':actual}
  for name in pred:row[name+'_previous_inflight']=sum(pred[name][str(q['simulator_request_id'])]>now for q in previous)
  rows.append(row)
 subset=[x for x in rows if x['case']==case.name]
 groups.append({'case':case.name,'requests':len(subset),'actual_any_previous_inflight':sum(x['actual_previous_inflight']>0 for x in subset),'dag_any_previous_inflight':sum(x['dag_previous_inflight']>0 for x in subset),'adapted_baseline_any_previous_inflight':sum(x['adapted_baseline_previous_inflight']>0 for x in subset),'dag_max_previous_inflight':max(x['dag_previous_inflight'] for x in subset),'adapted_baseline_max_previous_inflight':max(x['adapted_baseline_previous_inflight'] for x in subset)})
with (dest/'inflight.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
result={'status':'diagnostic_only','groups':groups,'scope':'Prior requests whose completion occurs strictly after each request server arrival; actual times from router, predicted completion from replay. Concurrent within-wave arrival staggering is retained. Counts do not measure queue size, causation, GPU concurrency, or simulator correctness.'};(dest/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
