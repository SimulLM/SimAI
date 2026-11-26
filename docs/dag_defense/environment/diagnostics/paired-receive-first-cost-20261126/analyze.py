import csv,json,pathlib,statistics,math,hashlib
source=pathlib.Path('/root/autodl-tmp/SimAI-handoff/docs/dag_defense/environment/diagnostics/receive-install-interval-20261126/samples.csv');out=pathlib.Path(__file__).parent
rows=list(csv.DictReader(source.open()));assert len(rows)==120
res=[];samples=[]
for length in (512,1024,2048):
 group=[r for r in rows if int(r['length'])==length];warm=[r for r in group if r['warmup']=='True']; measured=[r for r in group if r['warmup']=='False'];assert len(warm)==10 and len(measured)==30
 for r in group:
  start=int(r['receive_start_ns']);sync=int(r['install_sync_ns']);end=int(r['step_return_ns']);assert start<=sync<=end
  samples.append({'length':length,'wave':int(r['wave']),'warmup':r['warmup'],'decode_id':r['decode_id'],'receive_ns':start,'sync_ns':sync,'return_ns':end,'receive_ms':(sync-start)/1e6,'post_ms':(end-sync)/1e6,'combined_ms':(end-start)/1e6})
 xs=[x for x in samples if x['length']==length and x['warmup']=='False']
 def stats(key):
  v=sorted(x[key] for x in xs);return {'median':statistics.median(v),'min':v[0],'p95':v[math.ceil(.95*len(v))-1],'max':v[-1]}
 res.append({'input_tokens':length,'warmup':10,'measured':30,'receive_ms':stats('receive_ms'),'post_ms':stats('post_ms'),'combined_ms':stats('combined_ms')})
with (out/'paired.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=samples[0]);w.writeheader();w.writerows(samples)
result={'status':'paired_instrumented_candidate_not_frozen','rows':res,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'limitations':['intrusive per-tensor synchronization alters overlap','serial eight-output only; no concurrent coverage','different lengths share one session; no independent restart variance','combined interval excludes dispatch and router, not a physical additive component','no validation E2E fitting']}
(out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
