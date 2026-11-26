import csv,pathlib,json,hashlib
p=pathlib.Path(__file__).parent;original=pathlib.Path('/root/autodl-tmp/SimAI-handoff/docs/dag_defense/environment/diagnostics/uniform-forward-single-gpu-20261126/candidate-context-bins.csv');new=p/'coverage.csv'
with original.open() as f:rows=list(csv.DictReader(f));fields=list(rows[0])
keys={tuple(r[k] for k in ('input_tokens','actual_batch','rounded_mean_context','mixed_context')) for r in rows};added=[];overlap=[]
with new.open() as f:
 for r in csv.DictReader(f):
  assert r['eligible']=='1' and int(r['warmup_waves'])>=10 and int(r['measured_waves'])>=30
  key=tuple(r[k] for k in ('input_tokens','actual_batch','rounded_mean_context','mixed_context'))
  if key in keys:overlap.append({'key':key,'new_ms':r['median_forward_ms'],'kept':next(x['source'] for x in rows if tuple(x[k] for k in ('input_tokens','actual_batch','rounded_mean_context','mixed_context'))==key)});continue
  row={k:r[k] for k in fields if k!='source'};row['source']='single_gpu_uniform_targeted';rows.append(row);keys.add(key);added.append(key)
with (p/'candidate-context-bins.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
(p/'merge-audit.json').write_text(json.dumps({'source_hashes':{str(x):hashlib.sha256(x.read_bytes()).hexdigest() for x in (original,new)},'added':added,'duplicate_kept_original':overlap,'rows':len(rows),'frozen':False},indent=2)+'\n');print('added',len(added),'retained duplicate',len(overlap),'total',len(rows))
