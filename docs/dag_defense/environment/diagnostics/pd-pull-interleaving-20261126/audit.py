"""Audit prior instrumented receive steps between forwards of other requests."""
import bisect,collections,csv,hashlib,json,pathlib,tarfile
root=pathlib.Path(__file__).resolve().parent;src=root.parent/'pd-flow-boundary-20261126';trace=src/'derived-boundaries.csv';archive=src/'raw.tar.gz'
rows=[x for x in csv.DictReader(trace.open()) if x['warmup'].lower()=='false'];waves=collections.defaultdict(list);steps=collections.defaultdict(list)
for x in rows:waves[(x['input_tokens'],x['requested_batch'],x['wave'])].append(x)
with tarfile.open(archive) as t:
 for line in t.extractfile('compute-events-85025.jsonl'):
  e=json.loads(line)
  if e.get('event')=='model_step':
   for g in e.get('groups',[]):
    if not g['is_prompt']:steps[g['request_id']].append(e['host_start_ns'])
for seq in steps.values():seq.sort()
counts=collections.defaultdict(collections.Counter);details=[]
for (n,b,wave),rs in sorted(waves.items()):
 if len(rs)!=int(b):raise ValueError('incomplete wave')
 for t in sorted({int(x['decode_kv_step_host_start_ns']) for x in rs}):
  receivers=[x['decode_id'] for x in rs if int(x['decode_kv_step_host_start_ns'])==t];active=[]
  for x in rs:
   seq=steps[x['decode_id']+'-0'];i=bisect.bisect_left(seq,t)
   if 0<i<len(seq):active.append({'decode_id':x['decode_id'],'previous_forward_ns':seq[i-1],'next_forward_ns':seq[i]})
  counts[(n,b)]['receive_steps']+=1
  if active:counts[(n,b)]['receive_between_decode_steps']+=1
  details.append({'input_tokens':int(n),'requested_concurrency':int(b),'wave':int(wave),'receive_step_start_ns':t,'receivers':receivers,'ongoing_decode_requests':active})
summary={'scope':'Previously captured synchronized 8-output-token diagnostic; within-wave host step order only. A later Decode forward on the same request proves unfinished decode at this receive, but does not establish overlap or undisturbed timing.','source_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (trace,archive)},'groups':[{'input_tokens':int(k[0]),'requested_concurrency':int(k[1]),**dict(v)} for k,v in sorted(counts.items())],'total_interleaved_receive_steps':sum(x['receive_between_decode_steps'] if 'receive_between_decode_steps' in x else 0 for x in counts.values()),'detail_count':len(details)}
(root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');(root/'steps.jsonl').write_text(''.join(json.dumps(x,separators=(',',':'))+'\n' for x in details));print(json.dumps(summary,indent=2))
