"""Prepare deterministic, reviewable validation inputs; this does not freeze or run validation."""
import argparse,hashlib,json,pathlib,random,sys
MODEL='NousResearch/Llama-2-7b-hf';REV='8efe6c9b93655b934e27bd9981e3ec13e55aee9d';SEED=20261126
sha=lambda b:hashlib.sha256(b).hexdigest()
def encode(x):return (json.dumps(x,separators=(',',':'),ensure_ascii=True)+'\n').encode()
def create(root):
 root.mkdir(parents=True,exist_ok=False);rng=random.Random(SEED);cases=[(n,b,r) for n in (1024,2048) for b in (1,2,4) for r in range(5)];rng.shuffle(cases);seen=set();runs=[]
 for order,(n,b,r) in enumerate(cases):
  run_id=f'validation-{order:02d}-in{n}-wave{b}-rep{r}';path=root/(run_id+'.jsonl');records=[]
  for i in range(32):
   ids=[1]+[rng.randrange(4,32000) for _ in range(n-1)];digest=sha(encode(ids))
   if digest in seen:raise RuntimeError('duplicate token sequence')
   seen.add(digest);records.append({'run_id':run_id,'request_id':f'{run_id}-req{i:02d}','input_id':f'{run_id}-input{i:02d}','wave':i//b,'index_in_wave':i%b,'input_ids':ids,'input_sha256':digest})
  raw=b''.join(encode(x) for x in records);path.write_bytes(raw);runs.append({'order':order,'run_id':run_id,'input_tokens':n,'output_tokens':128,'concurrency':b,'repeat':r,'requests':32,'path':path.name,'sha256':sha(raw)})
 manifest={'status':'candidate_not_frozen','seed':SEED,'generator':'python random.Random MT19937; full token IDs stored','model':MODEL,'model_revision':REV,'bos_token_id':1,'generated_token_id_range':[4,31999],'tokenizer_note':'token IDs supplied directly; length must be verified by service before validation','dtype':'float16','tensor_parallel_size':1,'output_tokens':128,'sampling':{'temperature':0,'top_p':1,'seed':0,'ignore_eos':True,'min_tokens':128,'max_tokens':128},'schedule':'fixed-seed shuffled cases; each wave sends concurrency requests and waits for all; serial concurrency 1','run_count':30,'request_count':960,'runs':runs,'limitations':['candidate inputs only, no parameter freeze or validation','IDs selected from vocabulary; token text quality is not a criterion','warmup inputs must be distinct and excluded from measured window','record actual server arrival, completion, failure and timeout for every request']};(root/'candidate-manifest.json').write_bytes(encode(manifest));return check(root)
def check(root):
 m=json.loads((root/'candidate-manifest.json').read_text());errors=[];seen=set();cases=set();ids=set();count=0
 if m['run_count']!=30 or len(m['runs'])!=30 or m['request_count']!=960:errors.append('matrix cardinality')
 for order,run in enumerate(m['runs']):
  case=(run['input_tokens'],run['concurrency'],run['repeat']);cases.add(case);p=root/run['path'];raw=p.read_bytes()
  if run['order']!=order or sha(raw)!=run['sha256']:errors.append(f"manifest/order/hash {run['run_id']}")
  rows=[json.loads(x) for x in raw.splitlines()]
  if len(rows)!=32:errors.append(f"row count {run['run_id']}")
  for i,r in enumerate(rows):
   v=r['input_ids'];h=sha(encode(v));count+=1
   if r['request_id'] in ids or h in seen:errors.append(f'duplicate {r["request_id"]}')
   ids.add(r['request_id']);seen.add(h)
   if len(v)!=run['input_tokens'] or v[0]!=1 or any(not isinstance(x,int) or x<4 or x>=32000 for x in v[1:]) or h!=r['input_sha256'] or r['wave']!=i//run['concurrency'] or r['index_in_wave']!=i%run['concurrency'] or r['run_id']!=run['run_id']:errors.append(f'invalid input {r["request_id"]}')
 expected={(n,b,r) for n in (1024,2048) for b in (1,2,4) for r in range(5)}
 if cases!=expected or count!=960:errors.append('case coverage')
 result={'status':'candidate_checked' if not errors else 'failed','run_count':len(m['runs']),'request_count':count,'unique_requests':len(ids),'unique_inputs':len(seen),'manifest_sha256':sha((root/'candidate-manifest.json').read_bytes()),'errors':errors,'limits':['not a parameter freeze; service tokenizer/usage and model compatibility still need verification','no requests sent or validation run','fixed pseudo-random token IDs are synthetic inputs; they are not synthetic measurement results']};print(json.dumps(result,indent=2));return 0 if not errors else 1
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('action',choices=('create','check'));p.add_argument('--output',required=True,type=pathlib.Path);a=p.parse_args();sys.exit(create(a.output) if a.action=='create' else check(a.output))
