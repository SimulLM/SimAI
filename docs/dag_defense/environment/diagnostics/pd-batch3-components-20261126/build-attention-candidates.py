"""Produce separate candidate attention tables without silently pooling context shapes."""
import csv,hashlib,json,pathlib,sys
base,measure,out=map(pathlib.Path,sys.argv[1:]);out.mkdir(exist_ok=False)
with base.open(newline='') as f:
 reader=csv.DictReader(f);fields=reader.fieldnames;original=list(reader)
with measure.open(newline='') as f: components=list(csv.DictReader(f))
outputs={}
for kind,mixed in [('uniform','0'),('mixed','1')]:
 cells=[r for r in components if r['component']=='attention_combined' and r['mixed_context']==mixed and r['eligible']=='True']
 if {int(r['context_bin']) for r in cells}!=set(range(1040,1153,16)) or len(cells)!=8:raise ValueError('expected exactly eight eligible context bins')
 rows=list(original)
 for c in cells:
  context=c['context_bin']
  if any(r['batch_size']=='3' and r['prefill_chunk_size']=='0' and r['kv_cache_size']==context for r in rows):raise ValueError('existing cell would be overwritten')
  row=dict.fromkeys(fields,'0.0');row.update(n_embd=4096,n_q_head=32,n_kv_head=32,block_size=16,num_tensor_parallel_workers=1,batch_size=3,prefill_chunk_size=0,kv_cache_size=context);row['time_stats.attn_decode.median']=c['median_ms'];rows.append(row)
 path=out/(kind+'-attention.csv')
 with path.open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
 outputs[kind]={'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'added_cells':8}
result={'status':'diagnostic_candidates_not_frozen','base_sha256':hashlib.sha256(base.read_bytes()).hexdigest(),'component_sha256':hashlib.sha256(measure.read_bytes()).hexdigest(),'outputs':outputs,'scope':'Adds only layer-16 attention_combined CUDA event median to candidate attention profile, retaining uniform/mixed variants separately. No claim of service cost correctness; missing context selector, batch scheduling and CPU/KV overlap remain unresolved. Use same selected file for both comparators; no validation fitting.'}
(out/'manifest.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
