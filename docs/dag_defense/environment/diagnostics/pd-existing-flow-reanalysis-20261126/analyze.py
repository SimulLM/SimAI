"""Reanalyse previously captured instrumented host timestamps; no new measurements."""
import csv,json,pathlib,statistics,collections
root=pathlib.Path(__file__).resolve().parent
src=root.parent/'pd-flow-boundary-20261126'/'derived-boundaries.csv'
rows=list(csv.DictReader(src.open()));groups=collections.defaultdict(list)
for r in rows:
 if r['warmup'].lower()=='true':continue
 groups[(int(r['input_tokens']),int(r['requested_batch']))].append(r)
def pct(values,p):
 v=sorted(values);return v[round((len(v)-1)*p)]
def delta(r,a,b):return (int(r[b])-int(r[a]))/1e6
out=[]
for (length,concurrency),rs in sorted(groups.items()):
 result={'input_tokens':length,'requested_concurrency':concurrency,'requests':len(rs)}
 for label,a,b in [('submit_to_kv_step_ms','decode_submit_ns','decode_kv_step_host_start_ns'),('kv_step_to_recv_ms','decode_kv_step_host_start_ns','recv_api_start_ns'),('recv_host_ms','recv_api_start_ns','recv_api_return_ns'),('recv_return_to_step_sync_ms','recv_api_return_ns','kv_ready_upper_bound_after_step_sync_ns')]:
  v=[delta(r,a,b) for r in rs];result[label]={'median':statistics.median(v),'p95':pct(v,.95),'min':min(v),'max':max(v)}
 out.append(result)
(root/'summary.json').write_text(json.dumps({'scope':'Existing instrumented 8-output-token diagnostic, not uninstrumented E2E or exact transfer GPU time','warmup_excluded':True,'total_requests':sum(x['requests'] for x in out),'groups':out},indent=2)+'\n')
print(json.dumps(out,indent=2))
