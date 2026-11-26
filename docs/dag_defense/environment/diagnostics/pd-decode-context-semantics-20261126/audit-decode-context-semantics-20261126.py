import json,pathlib,collections,csv,hashlib
import sys
sys.path[:0]=['/root/autodl-tmp/SimAI-handoff/vidur-alibabacloud','/root/autodl-tmp/SimAI-handoff']
from vidur.entities.request import Request
p=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/pd-full-context-20261126');o=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/pd-decode-context-semantics-20261126');o.mkdir(exist_ok=False);load=lambda f:[json.loads(x) for x in f.read_text().splitlines()]
req=load(p/'client/requests.jsonl');routes={r['decode_id']:r for r in load(p/'router-events.jsonl') if r.get('decode_id')};rmap={routes[r['backend_request_id']]['decode_id']+'-0':r for r in req if r.get('backend_request_id') in routes and r['batch']==1};events=collections.defaultdict(list)
for f in p.glob('compute-events-*.jsonl'):
 for e in load(f):
  if e.get('event')!='model_step':continue
  ids=e.get('request_ids_to_seq_ids') or {};g=e.get('groups') or [];lens=e.get('seq_lens') or [];qs=e.get('query_lens') or []
  if len(ids)!=1 or len(g)!=1 or len(lens)!=1 or len(qs)!=1:continue
  rid=next(iter(ids))
  if rid in rmap and not g[0]['is_prompt'] and g[0]['request_id']==rid and qs[0]==1:events[rid].append((e['host_start_ns'],int(lens[0])))
rows=[];issues=[]
for rid,r in rmap.items():
 seq=[n for _,n in sorted(events[rid])];expected=list(range(r['length']+1,r['length']+128));good=seq==expected
 if not good:issues.append({'id':rid,'input':r['length'],'found_count':len(seq),'first':seq[:3],'last':seq[-3:]})
 rows.append({'backend_request_id':rid,'input_tokens':r['length'],'warmup':r['warmup'],'count':len(seq),'first':seq[0] if seq else '', 'last':seq[-1] if seq else '', 'expected_first':r['length']+1,'expected_last':r['length']+127,'exact_sequence_match':good})
with (o/'single-request-checks.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
source=pathlib.Path('/root/autodl-tmp/SimAI-handoff/vidur-alibabacloud/vidur/entities/request.py');predictor=pathlib.Path('/root/autodl-tmp/SimAI-handoff/vidur-alibabacloud/vidur/execution_time_predictor/sklearn_execution_time_predictor.py');sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest();sim={}
for n in (1024,2048):
 r=Request(0,n,128);r.on_batch_schedule(.5);r.on_batch_end(1,n);seq=[]
 for i in range(127):seq.append(r.num_processed_tokens);r.on_batch_end(i+2,1)
 sim[str(n)]={'sequence':seq,'complete':r.completed,'match':seq==list(range(n+1,n+128)) and r.completed}
result={'simulator_runtime':sim,'status':'single_request_context_alignment_verified' if len(rows)==80 and not issues and all(x['match'] for x in sim.values()) else 'incomplete','requests':len(rows),'issues':issues,'expected_rule':'after prefill simulator increments processed tokens by one; each subsequent decode batch increments one; feature uses processed_tokens, integer mean then ceil to 16','observed_rule':'single-request consumer vLLM forward seq_lens are input+1 through input+127 for 128 output','inputs':dict(collections.Counter(str(r['input_tokens']) for r in rows)),'source_sha256':{'simulator_request':sha(source),'simulator_predictor':sha(predictor)},'limits':['Only unambiguous single-request decode steps in one profiled runtime; does not prove mixed-batch order or non-instrumented scheduling','Aligned numerical context does not establish equivalent KVReady, first-token, CPU or transfer fee semantics','The profile uses full forward duration, not separate attention fee']};(o/'audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
