"""Build an explicitly classified candidate profile without overwriting old fees."""
import csv,hashlib,json,pathlib,sys
base,uniform,mixed,out=map(pathlib.Path,sys.argv[1:]);out.mkdir(exist_ok=False)
def load(p):
 with p.open(newline='') as f:
  r=csv.DictReader(f);return r.fieldnames,list(r)
fields,source=load(base);rows=[dict(r,context_shape='unclassified') for r in source]; contexts=set(map(str,range(1040,1153,16)))
for label,path in [('uniform',uniform),('mixed',mixed)]:
 columns,allrows=load(path)
 if columns!=fields or allrows[:len(source)]!=source:raise ValueError('candidate changed existing profile')
 extra=allrows[len(source):]
 if len(extra)!=8 or {r['kv_cache_size'] for r in extra}!=contexts or any(r['batch_size']!='3' or r['prefill_chunk_size']!='0' for r in extra):raise ValueError('unexpected candidate cells')
 rows.extend(dict(r,context_shape=label) for r in extra)
result=out/'attention.csv'
with result.open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=fields+['context_shape']);w.writeheader();w.writerows(rows)
manifest={'status':'candidate_not_frozen','original_rows':len(source),'uniform_rows':8,'mixed_rows':8,'sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (base,uniform,mixed,result)},'limitations':['Only actual batch 3 / 1024 input bins have classified shapes','Unclassified and interpolation fallback retain existing candidate behavior','Unsupported context spans or missing matching shape in classified bins fail closed','Mixed-context numerical correspondence with real batching remains unverified','Not a complete end-to-end cost or formal validation']}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(manifest,indent=2))
