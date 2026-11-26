"""Compare diagnostic real full-forward GPU intervals to candidate layer sums."""
import collections,csv,json,math,pathlib,re,statistics,sys
real=pathlib.Path(sys.argv[1]);ref=pathlib.Path(sys.argv[2]);cost=pathlib.Path(sys.argv[3]);out=pathlib.Path(sys.argv[4]);out.mkdir(parents=True,exist_ok=False)
a=json.loads(ref.read_text());router=a['router'];rid=router['decode_id']+'-0';events=[]
for file in (real/'service').glob('compute-events-*.jsonl'):
 for line in file.read_text().splitlines():
  e=json.loads(line)
  if rid in e.get('request_ids_to_seq_ids',{}) and e.get('query_lens')==[1]:events.append(e)
events.sort(key=lambda e:e['host_start_ns']);assert len(events)==63 and [e['seq_lens'] for e in events]==[[x] for x in range(513,576)]
groups=collections.defaultdict(list)
with cost.open() as f:
 for r in csv.DictReader(f):
  if r['graph_id'].startswith('replica1/') and r['op'] in ('attention.compute','mlp.compute'):groups[r['graph_id']].append(r)
by_iteration={}
for graph,rows in groups.items():
 match=re.fullmatch(r'replica1/stage0/batch(\d+)/iteration(\d+)',graph);assert match and match.group(1)==match.group(2)
 iteration=int(match.group(1));assert iteration not in by_iteration and len(rows)==64 and len({(x['op'],x['layer']) for x in rows})==64
 by_iteration[iteration]=sum(float(x['duration_s']) for x in rows)*1000
assert set(by_iteration)==set(range(1,64));rows=[]
for i,e in enumerate(events,1):
 measured=e['gpu_event_ms']['full_model_forward'];prediction=by_iteration[i];assert math.isfinite(measured) and measured>0
 rows.append({'iteration':i,'context_tokens':e['seq_lens'][0],'gpu_forward_ms':measured,'simulated_layer_sum_ms':prediction,'difference_ms':prediction-measured,'host_start_ns':e['host_start_ns'],'host_after_sync_ns':e['host_after_sync_ns']})
with (out/'iterations.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
result={'status':'single_repeated_request_diagnostic_only','input_sha256':a['input_sha256'],'iterations':len(rows),'gpu_forward_median_ms':statistics.median(x['gpu_forward_ms'] for x in rows),'simulated_layer_sum_median_ms':statistics.median(x['simulated_layer_sum_ms'] for x in rows),'difference_median_ms':statistics.median(x['difference_ms'] for x in rows),'difference_min_ms':min(x['difference_ms'] for x in rows),'difference_max_ms':max(x['difference_ms'] for x in rows),'limitations':['Real events are from a separate same-input repeat, not the original calibration request','One request gives 63 correlated steps, not 63 independent samples','GPU forward includes full model executable including embeddings/final norm but excludes connector, logits and sampler; simulation uses 32 layer components','GPU events and synchronization include instrumentation and possible stream gaps; cost boundaries are not identical','Calibration diagnostic only, no validation completion times used and no fee selected']};(out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
