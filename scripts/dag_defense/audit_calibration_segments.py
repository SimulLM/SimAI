"""Describe distinct real-router and simulator boundaries without equating them."""
import collections,csv,json,pathlib,statistics,sys
root=pathlib.Path(sys.argv[1]);dest=pathlib.Path(sys.argv[2]);dest.mkdir(exist_ok=False);rows=[];summaries=[]
for case in sorted(x for x in root.iterdir() if (x/'request-map.json').exists()):
 mode,rep=case.name.split('-');source=pathlib.Path('/root/autodl-tmp/dag-handoff/runs')/f'calibration-{mode}-independent-20261126'/f'server-{rep}/router-events.jsonl';events=collections.defaultdict(lambda:collections.defaultdict(list))
 for line in source.open():
  e=json.loads(line);events[e['request_id']][e['event']].append(e)
 mapping=json.loads((case/'request-map.json').read_text());files=list((case/'dag').glob('*/pd-summary.json'))
 if len(files)!=1:raise ValueError('ambiguous DAG summary')
 summary=json.loads(files[0].read_text());m={x['request_id']:x for x in summary['migrations']}
 if summary['status']!='completed' or set(m)!={str(x['simulator_request_id']) for x in mapping}:raise ValueError('missing migration')
 subset=[]
 for r in mapping:
  ev=events[r['router_id']];names=['server_arrival','prefill_response','server_first_token','server_complete']
  if any(len(ev[n])!=1 or ev[n][0].get('clock_id')!='CLOCK_MONOTONIC' for n in names):raise ValueError('missing, duplicate or wrong clock')
  t={n:ev[n][0]['timestamp_ns'] for n in names}
  if list(t.values())!=sorted(t.values()) or t['server_arrival']!=r['server_arrival_ns'] or t['server_complete']!=r['server_complete_ns']:raise ValueError('real timing mismatch')
  sim=m[str(r['simulator_request_id'])];start=sim['first_decode_start_s'];end=sim['completed_at_s']
  if start is None or end is None or end<start:raise ValueError('invalid simulator timing')
  row={'case':case.name,'simulator_request_id':r['simulator_request_id'],'router_id':r['router_id'],'router_arrival_to_prefill_response_s':(t['prefill_response']-t['server_arrival'])/1e9,'router_arrival_to_first_token_s':(t['server_first_token']-t['server_arrival'])/1e9,'router_first_token_to_complete_s':(t['server_complete']-t['server_first_token'])/1e9,'sim_first_decode_start_to_complete_s':end-start};rows.append(row);subset.append(row)
 summaries.append({'case':case.name,'requests':len(subset),**{f'median_{k}':statistics.median(r[k] for r in subset) for k in ('router_arrival_to_prefill_response_s','router_arrival_to_first_token_s','router_first_token_to_complete_s','sim_first_decode_start_to_complete_s')}})
with (dest/'segments.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
result={'status':'diagnostic_only','cases':summaries,'limitations':['router first-token event derives from streamed usage; not a GPU event','simulator first Decode start is a different boundary and does not equal router first-token time','simulator Decode start-to-completion includes the first modeled Decode step; router first-token-to-completion begins after first emitted token','These summaries cannot be added or subtracted as matched component fees','No validation or accuracy claim']};(dest/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
